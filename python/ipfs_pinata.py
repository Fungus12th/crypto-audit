"""
Pinata IPFS Integration for Merkle Root Hybrid Storage.
Handles off-chain pinning of dataset files and Merkle audit manifests.
"""

import hashlib
import json
import os
import requests

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
    # Check if placeholder
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


def pin_json_to_pinata(data, name="dataset_manifest.json"):
    """Pin arbitrary JSON metadata (such as an audit manifest) to Pinata."""
    jwt = get_pinata_jwt()
    gateway = get_pinata_gateway()

    if not jwt:
        # Generate deterministic CID from json content
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


def pin_files_to_pinata(saved_file_paths, folder_name="dataset"):
    """
    Pins a list of file paths to Pinata IPFS under a common directory.
    saved_file_paths: list of (filename, absolute_filepath)
    """
    jwt = get_pinata_jwt()
    gateway = get_pinata_gateway()

    if not jwt:
        # Generate simulated IPFS CID based on combined files content hash
        combined = hashlib.sha256()
        for fname, fpath in saved_file_paths:
            combined.update(fname.encode("utf-8"))
            try:
                with open(fpath, "rb") as f:
                    combined.update(f.read())
            except Exception:
                pass
        sim_cid = "Qm" + combined.hexdigest()[:44]
        return {
            "success": True,
            "mode": "simulation",
            "cid": sim_cid,
            "gateway_url": f"https://{gateway}/ipfs/{sim_cid}",
            "is_simulated": True,
        }

    url = "https://api.pinata.cloud/pinning/pinFileToIPFS"
    headers = {"Authorization": f"Bearer {jwt}"}

    opened_files = []
    files_payload = []

    try:
        is_single = len(saved_file_paths) == 1

        for fname, fpath in saved_file_paths:
            f = open(fpath, "rb")
            opened_files.append(f)
            # If single file, pin without folder prefix so CID serves file directly;
            # If multiple files, use folder_name/filename directory packaging.
            file_key = fname if is_single else f"{folder_name}/{fname}"
            files_payload.append(
                ("file", (file_key, f, "application/octet-stream"))
            )

        metadata = json.dumps({"name": saved_file_paths[0][0] if is_single else folder_name})
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
                file_urls = {saved_file_paths[0][0]: gw_url}
            else:
                gw_url = f"https://{gateway}/ipfs/{cid}/{saved_file_paths[0][0]}"
                file_urls = {fname: f"https://{gateway}/ipfs/{cid}/{fname}" for fname, _ in saved_file_paths}

            return {
                "success": True,
                "mode": "live_pinata",
                "cid": cid,
                "gateway_url": gw_url,
                "file_urls": file_urls,
                "is_directory": not is_single,
                "pin_size": res_json.get("PinSize"),
                "timestamp": res_json.get("Timestamp"),
                "is_simulated": False,
            }
        else:
            raise Exception(f"Pinata pinFileToIPFS returned {resp.status_code}: {resp.text}")

    except Exception as e:
        print(f"Warning: Pinata pinFileToIPFS error ({e}), falling back to deterministic CID")
        combined = hashlib.sha256()
        for fname, _ in saved_file_paths:
            combined.update(fname.encode("utf-8"))
        sim_cid = "Qm" + combined.hexdigest()[:44]
        return {
            "success": True,
            "mode": "simulation",
            "cid": sim_cid,
            "gateway_url": f"https://{gateway}/ipfs/{sim_cid}",
            "error": str(e),
            "is_simulated": True,
        }
    finally:
        for f in opened_files:
            try:
                f.close()
            except Exception:
                pass
