"""
Pinata IPFS Integration for Merkle Root Hybrid Storage.
Handles off-chain pinning of dataset files and Merkle audit manifests.
Includes Zero-Trust Convergent Envelope Encryption (AES-CBC/Fernet keyed by file SHA-256).
"""

import base64
import hashlib
import json
import os
import tempfile
import requests

try:
    from cryptography.fernet import Fernet
    HAS_CRYPTOGRAPHY = True
except ImportError:
    HAS_CRYPTOGRAPHY = False


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ENV_FILE = os.path.join(PROJECT_ROOT, ".env")


def load_env():
    """Load key-value pairs from .env into os.environ if not already set."""
    if os.path.isfile(ENV_FILE):
        try:
            with open(ENV_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip('"').strip("'")
                        if k and k not in os.environ:
                            os.environ[k] = v
        except Exception as e:
            print(f"Notice: could not load .env: {e}")


load_env()


def get_pinata_jwt():
    """Retrieve Pinata JWT token."""
    load_env()
    token = os.environ.get("PINATA_JWT", "").strip()
    if not token or token == "your_pinata_jwt_here" or len(token) < 20:
        return None
    return token


_CACHED_GATEWAY = None


def get_pinata_gateway():
    """Retrieve Pinata Gateway domain, auto-discovering dedicated domain if available."""
    global _CACHED_GATEWAY
    load_env()
    gw = os.environ.get("PINATA_GATEWAY", "").strip()
    if gw and gw != "gateway.pinata.cloud":
        return gw

    if _CACHED_GATEWAY:
        return _CACHED_GATEWAY

    # Auto-discover dedicated gateway from Pinata API
    jwt = get_pinata_jwt()
    if jwt:
        try:
            resp = requests.get(
                "https://api.pinata.cloud/v3/ipfs/gateways",
                headers={"Authorization": f"Bearer {jwt}"},
                timeout=5,
            )
            if resp.status_code == 200:
                rows = resp.json().get("data", {}).get("rows", [])
                if rows and rows[0].get("domain"):
                    domain = rows[0]["domain"]
                    if not domain.endswith(".mypinata.cloud"):
                        domain = f"{domain}.mypinata.cloud"
                    _CACHED_GATEWAY = domain
                    return _CACHED_GATEWAY
        except Exception:
            pass

    return gw or "gateway.pinata.cloud"


def is_pinata_configured():
    """Check if a valid Pinata JWT is present."""
    return get_pinata_jwt() is not None


def test_pinata_auth():
    """Test Pinata API authentication."""
    jwt = get_pinata_jwt()
    if not jwt:
        return {
            "authenticated": False,
            "mode": "simulation",
            "message": "PINATA_JWT not configured in .env. Running in simulated IPFS mode.",
        }

    url = "https://api.pinata.cloud/data/testAuthentication"
    headers = {"Authorization": f"Bearer {jwt}"}
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            return {
                "authenticated": True,
                "mode": "live_pinata",
                "message": resp.json().get("message", "Authenticated successfully with Pinata IPFS"),
            }
        else:
            return {
                "authenticated": False,
                "mode": "simulation",
                "message": f"Pinata auth failed ({resp.status_code}): {resp.text}",
            }
    except Exception as e:
        return {
            "authenticated": False,
            "mode": "simulation",
            "message": f"Connection to Pinata failed: {e}",
        }


# ─── Zero-Trust Convergent / Envelope Encryption ────────────────────

def derive_convergent_key(file_hash):
    """Derive 32-byte Fernet key from file SHA-256 hash."""
    clean_hash = file_hash.lower().replace("0x", "")
    try:
        hash_bytes = bytes.fromhex(clean_hash)
    except Exception:
        hash_bytes = clean_hash.encode("utf-8")
    raw_key = hashlib.sha256(b"convergent-encryption-v1:" + hash_bytes).digest()
    return base64.urlsafe_b64encode(raw_key)


def encrypt_envelope(data_bytes, file_hash):
    """
    Encrypt file bytes using key derived from its own SHA-256 hash.
    Only the holder of the uncorrupted file (or its hash) can decrypt it.
    """
    if HAS_CRYPTOGRAPHY:
        key = derive_convergent_key(file_hash)
        fernet = Fernet(key)
        return fernet.encrypt(data_bytes)
    else:
        # XOR-HMAC fallback if cryptography module is missing
        key_bytes = hashlib.sha256(file_hash.encode("utf-8")).digest()
        encrypted = bytearray(b ^ key_bytes[i % 32] for i, b in enumerate(data_bytes))
        hmac_tag = hashlib.sha256(key_bytes + encrypted).digest()
        return bytes(hmac_tag + encrypted)


def decrypt_envelope(encrypted_bytes, file_hash):
    """Decrypt payload using key derived from file SHA-256 hash."""
    if HAS_CRYPTOGRAPHY:
        key = derive_convergent_key(file_hash)
        fernet = Fernet(key)
        return fernet.decrypt(encrypted_bytes)
    else:
        key_bytes = hashlib.sha256(file_hash.encode("utf-8")).digest()
        tag = encrypted_bytes[:32]
        data = encrypted_bytes[32:]
        expected_tag = hashlib.sha256(key_bytes + data).digest()
        if tag != expected_tag:
            raise ValueError("Integrity check failed during decryption")
        return bytes(b ^ key_bytes[i % 32] for i, b in enumerate(data))


# ─── Pinning Operations ─────────────────────────────────────────────

def pin_json_to_pinata(data, name="dataset_manifest.json"):
    """Pin arbitrary JSON metadata (such as an audit manifest) to Pinata."""
    jwt = get_pinata_jwt()
    gateway = get_pinata_gateway()

    if not jwt:
        content_bytes = json.dumps(data, sort_keys=True).encode("utf-8")
        sim_hash = hashlib.sha256(content_bytes).hexdigest()[:44]
        sim_cid = f"bafybeih{sim_hash}"
        return {
            "success": True,
            "mode": "simulation",
            "cid": sim_cid,
            "gateway_url": f"https://{gateway}/ipfs/{sim_cid}",
            "is_simulated": True,
        }

    url = "https://api.pinata.cloud/pinning/pinJSONToIPFS"
    headers = {
        "Authorization": f"Bearer {jwt}",
        "Content-Type": "application/json",
    }
    payload = {
        "pinataContent": data,
        "pinataMetadata": {"name": name},
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=25)
        if resp.status_code in (200, 201):
            res_json = resp.json()
            cid = res_json.get("IpfsHash")
            return {
                "success": True,
                "mode": "live_pinata",
                "cid": cid,
                "gateway_url": f"https://{gateway}/ipfs/{cid}",
                "pin_size": res_json.get("PinSize"),
                "timestamp": res_json.get("Timestamp"),
                "is_simulated": False,
            }
        else:
            raise Exception(f"Pinata returned {resp.status_code}: {resp.text}")
    except Exception as e:
        print(f"Warning: pinJSONToIPFS failed ({e}), falling back to simulated CID")
        content_bytes = json.dumps(data, sort_keys=True).encode("utf-8")
        sim_cid = "bafybeih" + hashlib.sha256(content_bytes).hexdigest()[:44]
        return {
            "success": True,
            "mode": "simulation",
            "cid": sim_cid,
            "gateway_url": f"https://{gateway}/ipfs/{sim_cid}",
            "error": str(e),
            "is_simulated": True,
        }


def pin_files_to_pinata(saved_file_paths, folder_name="dataset", encrypt=False, file_hashes=None):
    """
    Pins a list of file paths to Pinata IPFS under a common directory.
    saved_file_paths: list of (filename, absolute_filepath)
    encrypt: if True, encrypts files with convergent key before pinning.
    file_hashes: optional dict mapping filename -> sha256 hex string for encryption.
    """
    jwt = get_pinata_jwt()
    gateway = get_pinata_gateway()
    temp_enc_files = []

    # Handle envelope encryption if requested
    paths_to_pin = saved_file_paths
    if encrypt and file_hashes:
        enc_paths = []
        for fname, fpath in saved_file_paths:
            h = file_hashes.get(fname)
            if h:
                try:
                    with open(fpath, "rb") as original_file:
                        plain_data = original_file.read()
                    enc_data = encrypt_envelope(plain_data, h)
                    tmp = tempfile.NamedTemporaryFile(delete=False)
                    tmp.write(enc_data)
                    tmp.close()
                    temp_enc_files.append(tmp.name)
                    enc_paths.append((f"{fname}.enc", tmp.name))
                except Exception as ex:
                    print(f"Notice: envelope encryption failed for {fname}: {ex}")
                    enc_paths.append((fname, fpath))
            else:
                enc_paths.append((fname, fpath))
        paths_to_pin = enc_paths

    if not jwt:
        combined = hashlib.sha256()
        for fname, fpath in paths_to_pin:
            combined.update(fname.encode("utf-8"))
            try:
                with open(fpath, "rb") as f:
                    combined.update(f.read())
            except Exception:
                pass
        sim_cid = "Qm" + combined.hexdigest()[:44]
        _cleanup_temp_files(temp_enc_files)
        return {
            "success": True,
            "mode": "simulation",
            "cid": sim_cid,
            "gateway_url": f"https://{gateway}/ipfs/{sim_cid}",
            "is_encrypted": encrypt,
            "is_simulated": True,
        }

    url = "https://api.pinata.cloud/pinning/pinFileToIPFS"
    headers = {"Authorization": f"Bearer {jwt}"}
    opened_files = []
    files_payload = []

    try:
        is_single = len(paths_to_pin) == 1

        for fname, fpath in paths_to_pin:
            f = open(fpath, "rb")
            opened_files.append(f)
            file_key = fname if is_single else f"{folder_name}/{fname}"
            files_payload.append(
                ("file", (file_key, f, "application/octet-stream"))
            )

        metadata = json.dumps({"name": paths_to_pin[0][0] if is_single else folder_name})
        data_payload = {"pinataMetadata": metadata}

        resp = requests.post(
            url,
            headers=headers,
            files=files_payload,
            data=data_payload,
            timeout=60,
        )

        if resp.status_code in (200, 201):
            res_json = resp.json()
            cid = res_json.get("IpfsHash")

            if is_single:
                gw_url = f"https://{gateway}/ipfs/{cid}"
                file_urls = {paths_to_pin[0][0]: gw_url}
            else:
                gw_url = f"https://{gateway}/ipfs/{cid}/{paths_to_pin[0][0]}"
                file_urls = {fname: f"https://{gateway}/ipfs/{cid}/{fname}" for fname, _ in paths_to_pin}

            return {
                "success": True,
                "mode": "live_pinata",
                "cid": cid,
                "gateway_url": gw_url,
                "file_urls": file_urls,
                "is_directory": not is_single,
                "is_encrypted": encrypt,
                "pin_size": res_json.get("PinSize"),
                "timestamp": res_json.get("Timestamp"),
                "is_simulated": False,
            }
        else:
            raise Exception(f"Pinata pinFileToIPFS returned {resp.status_code}: {resp.text}")

    except Exception as e:
        print(f"Warning: Pinata pinFileToIPFS error ({e}), falling back to deterministic CID")
        combined = hashlib.sha256()
        for fname, _ in paths_to_pin:
            combined.update(fname.encode("utf-8"))
        sim_cid = "Qm" + combined.hexdigest()[:44]
        return {
            "success": True,
            "mode": "simulation",
            "cid": sim_cid,
            "gateway_url": f"https://{gateway}/ipfs/{sim_cid}",
            "is_encrypted": encrypt,
            "error": str(e),
            "is_simulated": True,
        }
    finally:
        for f in opened_files:
            try:
                f.close()
            except Exception:
                pass
        _cleanup_temp_files(temp_enc_files)


def _cleanup_temp_files(file_list):
    """Safely unlink temporary encrypted files."""
    for path in file_list:
        try:
            if os.path.isfile(path):
                os.unlink(path)
        except Exception:
            pass


def unpin_hash(cid):
    """Unpin a CID from Pinata."""
    jwt = get_pinata_jwt()
    if not jwt:
        return {"success": True, "message": "Simulated unpin successful"}

    url = f"https://api.pinata.cloud/pinning/unpin/{cid}"
    headers = {"Authorization": f"Bearer {jwt}"}
    try:
        resp = requests.delete(url, headers=headers, timeout=15)
        return {"success": resp.status_code in (200, 204), "status_code": resp.status_code}
    except Exception as e:
        return {"success": False, "error": str(e)}
