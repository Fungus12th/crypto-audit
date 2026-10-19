"""
Flask API server for Merkle Root frontend.
Wraps existing merkle.py / audit.py / blockchain scripts.
"""

import hashlib
import json
import os
import sys
import tempfile
import shutil
from datetime import datetime, timezone

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

# Add the python directory to path so we can import merkle
sys.path.insert(0, os.path.dirname(__file__))
from merkle import hash_file, hash_dataset, build_tree, get_root, generate_proof, verify_proof
from ipfs_pinata import (
    pin_files_to_pinata,
    pin_json_to_pinata,
    is_pinata_configured,
    test_pinata_auth,
    get_pinata_gateway,
    get_pinata_jwt,
    ENV_FILE,
)

# ─── App setup ────────────────────────────────────────────────────────

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
FRONTEND_DIR = os.path.join(PROJECT_ROOT, "frontend")
UPLOAD_DIR = os.path.join(PROJECT_ROOT, "uploads")
REGISTRY_FILE = os.path.join(PROJECT_ROOT, "dataset_registry.json")
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = Flask(__name__, static_folder=FRONTEND_DIR)
CORS(app)


def parse_notes_ipfs(notes_raw, root_hex=""):
    """Extract IPFS CID, gateway URL, and manifest CID from contract notes string."""
    if not notes_raw:
        return "", "", ""
    try:
        data = json.loads(notes_raw)
        cid = data.get("ipfs_cid", "")
        manifest_cid = data.get("manifest_cid", "")
        gw_domain = get_pinata_gateway()

        # If local registry has the files for this root, link directly to the primary file
        # to avoid Pinata's ERR_ID:00023 directory listing block on *.mypinata.cloud
        reg = load_dataset_registry()
        reg_item = reg.get(root_hex, {}) if root_hex else {}
        files = reg_item.get("files", [])

        if files:
            first_fname = files[0].get("name", "")
            # If notes already contain a direct file path, keep it
            raw_gw = data.get("gateway", "")
            if raw_gw and first_fname in raw_gw:
                gateway = raw_gw
            elif first_fname:
                gateway = f"https://{gw_domain}/ipfs/{cid}/{first_fname}"
            else:
                gateway = f"https://{gw_domain}/ipfs/{cid}"
        else:
            gateway = data.get("gateway", "") or (f"https://{gw_domain}/ipfs/{cid}" if cid else "")

        return cid, gateway, manifest_cid
    except Exception:
        if notes_raw.startswith("Qm") or notes_raw.startswith("bafy"):
            gw_domain = get_pinata_gateway()
            return notes_raw, f"https://{gw_domain}/ipfs/{notes_raw}", ""
        return "", "", ""



def load_dataset_registry():
    """Load persistent registry of known datasets and their Merkle trees."""
    if os.path.isfile(REGISTRY_FILE):
        try:
            with open(REGISTRY_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_dataset_registry(registry):
    """Save persistent registry of datasets."""
    try:
        with open(REGISTRY_FILE, "w") as f:
            json.dump(registry, f, indent=2)
    except Exception as e:
        print(f"Warning: Failed to save registry: {e}")


def index_local_data_folder():
    """Index default PROJECT_ROOT/data folder into registry if available."""
    data_folder = os.path.join(PROJECT_ROOT, "data")
    if os.path.isdir(data_folder):
        try:
            file_hashes = hash_dataset(data_folder)
            if file_hashes:
                leaf_hashes = [h for _, h in file_hashes]
                tree = build_tree(leaf_hashes)
                root = get_root(tree)
                tree_data = [
                    {"level": idx, "nodes": [h[:16] + "..." for h in lvl], "full_nodes": lvl}
                    for idx, lvl in enumerate(tree)
                ]
                reg = load_dataset_registry()
                reg[root] = {
                    "root": root,
                    "version": "v1.0 (Genesis)",
                    "creator": "System Core",
                    "folder": data_folder,
                    "file_count": len(file_hashes),
                    "files": [
                        {"name": rp, "hash": h[:16] + "...", "full_hash": h}
                        for rp, h in file_hashes
                    ],
                    "tree": tree_data,
                    "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
                }
                save_dataset_registry(reg)
        except Exception as e:
            print(f"Notice: could not index data folder: {e}")


# Run initial indexing on server import
index_local_data_folder()



# ─── Static file serving ─────────────────────────────────────────────

@app.route("/")
def serve_index():
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.route("/<path:filename>")
def serve_static(filename):
    return send_from_directory(FRONTEND_DIR, filename)


# ─── Auth: Demo accounts & login ─────────────────────────────────────

import secrets
import time

# Demo accounts (in a real app this would be a database)
DEMO_ACCOUNTS = {
    "user": [
        {"id": "USR-001", "username": "alice", "password": "alice123", "name": "Alice Nakamoto", "role": "user"},
        {"id": "USR-002", "username": "bob", "password": "bob123", "name": "Bob Finney", "role": "user"},
    ],
    "company": [
        {"id": "ORG-001", "username": "acme", "password": "acme123", "name": "Acme AI Labs", "role": "company"},
        {"id": "ORG-002", "username": "nexus", "password": "nexus123", "name": "Nexus Data Corp", "role": "company"},
    ],
}

# Active sessions: token -> {account_info, role, expires}
active_sessions = {}


@app.route("/api/login", methods=["POST"])
def api_login():
    """Authenticate a user or company and return a session token."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No credentials provided"}), 400

    username = data.get("username", "").strip().lower()
    password = data.get("password", "").strip()
    role = data.get("role", "").strip().lower()  # "user" or "company"

    if not username or not password or role not in ("user", "company"):
        return jsonify({"error": "Username, password, and role are required"}), 400

    # Find matching account
    account = None
    for acc in DEMO_ACCOUNTS.get(role, []):
        if acc["username"] == username and acc["password"] == password:
            account = acc
            break

    if not account:
        return jsonify({"error": "Invalid username or password"}), 401

    # Generate session token
    token = secrets.token_hex(32)
    active_sessions[token] = {
        "id": account["id"],
        "username": account["username"],
        "name": account["name"],
        "role": account["role"],
        "login_time": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "expires": time.time() + 86400,  # 24 hours
    }

    return jsonify({
        "success": True,
        "token": token,
        "id": account["id"],
        "name": account["name"],
        "role": account["role"],
    })


@app.route("/api/session", methods=["GET"])
def api_session():
    """Validate a session token and return account info."""
    token = request.headers.get("Authorization", "").replace("Bearer ", "").strip()
    if not token or token not in active_sessions:
        return jsonify({"authenticated": False}), 401

    session = active_sessions[token]
    if time.time() > session["expires"]:
        del active_sessions[token]
        return jsonify({"authenticated": False, "error": "Session expired"}), 401

    return jsonify({
        "authenticated": True,
        "id": session["id"],
        "name": session["name"],
        "role": session["role"],
        "login_time": session["login_time"],
    })


@app.route("/api/logout", methods=["POST"])
def api_logout():
    """Invalidate a session token."""
    token = request.headers.get("Authorization", "").replace("Bearer ", "").strip()
    if token in active_sessions:
        del active_sessions[token]
    return jsonify({"success": True})


# ─── API: Hash a dataset folder ──────────────────────────────────────

@app.route("/api/hash-dataset", methods=["POST"])
def api_hash_dataset():
    """
    Accepts multiple file uploads, builds Merkle tree, returns root + tree info.
    Files are uploaded as multipart form data under the key 'files'.
    """
    if "files" not in request.files:
        return jsonify({"error": "No files uploaded"}), 400

    files = request.files.getlist("files")
    if not files or files[0].filename == "":
        return jsonify({"error": "No files selected"}), 400

    # Save uploaded files to a temp directory
    temp_dir = tempfile.mkdtemp(dir=UPLOAD_DIR)
    saved_files = []

    try:
        for f in files:
            # Preserve relative paths from webkitdirectory if present
            filename = f.filename.replace("\\", "/")
            # Use just the basename to keep things flat
            safe_name = os.path.basename(filename)
            if not safe_name:
                continue
            filepath = os.path.join(temp_dir, safe_name)
            f.save(filepath)
            saved_files.append(safe_name)

        # Hash and build tree
        file_hashes = hash_dataset(temp_dir)
        if not file_hashes:
            return jsonify({"error": "No valid files found"}), 400

        leaf_hashes = [h for _, h in file_hashes]
        tree = build_tree(leaf_hashes)
        root = get_root(tree)

        # Build tree visualization data
        tree_data = []
        for level_idx, level in enumerate(tree):
            tree_data.append({
                "level": level_idx,
                "nodes": [h[:16] + "..." for h in level]
            })

        result = {
            "root": root,
            "file_count": len(file_hashes),
            "tree_levels": len(tree),
            "files": [
                {"name": name, "hash": h[:16] + "...", "full_hash": h}
                for name, h in file_hashes
            ],
            "tree": tree_data,
            "temp_id": os.path.basename(temp_dir),
        }

        # ─── Hybrid Storage: Pin to Pinata IPFS ───────────────────────
        saved_file_tuples = [(name, os.path.join(temp_dir, name)) for name in saved_files]
        ipfs_files_res = pin_files_to_pinata(saved_file_tuples, folder_name=f"dataset_{root[:10]}")

        file_urls = ipfs_files_res.get("file_urls", {})
        result["files"] = [
            {
                "name": name,
                "hash": h[:16] + "...",
                "full_hash": h,
                "ipfs_url": file_urls.get(name, f"{ipfs_files_res.get('gateway_url')}/{name}" if ipfs_files_res.get("is_directory") else ipfs_files_res.get("gateway_url")),
            }
            for name, h in file_hashes
        ]

        manifest_payload = {
            "title": "Merkle Root Audit Manifest",
            "merkle_root": root,
            "tree_levels": len(tree),
            "file_count": len(file_hashes),
            "files": [
                {"name": name, "sha256": h}
                for name, h in file_hashes
            ],
            "ipfs_directory_cid": ipfs_files_res.get("cid"),
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        }
        ipfs_manifest_res = pin_json_to_pinata(manifest_payload, name=f"manifest_{root[:10]}.json")

        result["ipfs_cid"] = ipfs_files_res.get("cid")
        result["ipfs_gateway"] = ipfs_files_res.get("gateway_url")
        result["ipfs_mode"] = ipfs_files_res.get("mode")
        result["manifest_cid"] = ipfs_manifest_res.get("cid")
        result["manifest_gateway"] = ipfs_manifest_res.get("gateway_url")

        # Save to persistent dataset registry
        reg = load_dataset_registry()
        reg[root] = {
            "root": root,
            "version": "v1.0 (Pending submission)",
            "creator": "Company Portal",
            "folder": temp_dir,
            "file_count": len(file_hashes),
            "files": result["files"],
            "tree": tree_data,
            "ipfs_cid": ipfs_files_res.get("cid"),
            "ipfs_gateway": ipfs_files_res.get("gateway_url"),
            "ipfs_mode": ipfs_files_res.get("mode"),
            "manifest_cid": ipfs_manifest_res.get("cid"),
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        }
        save_dataset_registry(reg)

        return jsonify(result)

    except Exception as e:
        shutil.rmtree(temp_dir, ignore_errors=True)
        return jsonify({"error": str(e)}), 500


# ─── API: Verify a single file against all known datasets ─────────────

@app.route("/api/verify", methods=["POST"])
def api_verify():
    """
    User uploads a single file. The server automatically:
    1. Scans all stored dataset sessions and registry for a matching file hash
    2. Generates cryptographic Merkle proof for inclusion
    3. Cross-references the dataset's Merkle root with on-chain records
    4. Returns whether the file is verified (included in an audited dataset)

    No manual root or session ID required — the blockchain is public.
    """
    file_hash = None
    input_file_name = None
    temp_file_path = None

    if "file" in request.files and request.files["file"].filename != "":
        f = request.files["file"]
        input_file_name = f.filename
        temp_file = tempfile.NamedTemporaryFile(dir=UPLOAD_DIR, delete=False)
        f.save(temp_file.name)
        temp_file_path = temp_file.name
        file_hash = hash_file(temp_file_path)
    else:
        # Check for JSON or form body with hash
        data = request.get_json(silent=True) or request.form or {}
        raw_hash = data.get("hash") or data.get("file_hash") or data.get("hash_input", "")
        if raw_hash:
            raw_hash = str(raw_hash).strip().lower()
            if raw_hash.startswith("0x"):
                raw_hash = raw_hash[2:]
            if len(raw_hash) == 64 and all(c in "0123456789abcdef" for c in raw_hash):
                file_hash = raw_hash
                input_file_name = f"Hash: {file_hash[:16]}..."
            else:
                return jsonify({"error": "Invalid SHA-256 hash. Must be a 64-character hexadecimal string."}), 400
        else:
            return jsonify({"error": "Please select a file or provide a 64-character SHA-256 hash."}), 400

    try:

        # Collect on-chain roots for cross-referencing
        on_chain_roots = {}
        try:
            from web3 import Web3
            w3 = Web3(Web3.HTTPProvider("http://127.0.0.1:8545"))
            if w3.is_connected():
                address_file = os.path.join(PROJECT_ROOT, "deployed_address.json")
                if os.path.isfile(address_file):
                    with open(address_file) as f:
                        contract_address = json.load(f)["address"]
                    abi_file = os.path.join(
                        PROJECT_ROOT, "artifacts", "contracts",
                        "AuditRegistry.sol", "AuditRegistry.json"
                    )
                    with open(abi_file) as f:
                        contract_abi = json.load(f)["abi"]
                    contract = w3.eth.contract(
                        address=Web3.to_checksum_address(contract_address),
                        abi=contract_abi,
                    )
                    count = contract.functions.getRecordCount().call()
                    for i in range(count):
                        result = contract.functions.getRecord(i).call()
                        root_hex = result[0].hex()
                        cid, gateway, manifest_cid = parse_notes_ipfs(result[3], root_hex)
                        on_chain_roots[root_hex] = {
                            "id": i,
                            "version": result[1],
                            "creator": result[2],
                            "notes": result[3],
                            "ipfs_cid": cid,
                            "ipfs_gateway": gateway,
                            "manifest_cid": manifest_cid,
                            "submitted_by": result[4],
                            "timestamp": datetime.fromtimestamp(
                                result[5], tz=timezone.utc
                            ).strftime("%Y-%m-%d %H:%M:%S UTC"),
                        }
        except Exception:
            pass  # blockchain unavailable — still check local datasets

        # Scan all datasets in registry and UPLOAD_DIR
        reg = load_dataset_registry()
        matches = []

        # 1. Check datasets in registry
        for root_key, meta in reg.items():
            files_list = meta.get("files", [])
            leaf_hashes = [f["full_hash"] for f in files_list]
            leaf_index = None
            matched_filename = None

            for i, f_obj in enumerate(files_list):
                if f_obj.get("full_hash") == file_hash:
                    leaf_index = i
                    matched_filename = f_obj.get("name")
                    break

            if leaf_index is not None and leaf_hashes:
                try:
                    tree = build_tree(leaf_hashes)
                    computed_root = get_root(tree)
                    proof = generate_proof(tree, leaf_index)
                    is_valid = verify_proof(file_hash, proof, root_key)

                    tree_data = [
                        {"level": idx, "nodes": [h[:16] + "..." for h in lvl]}
                        for idx, lvl in enumerate(tree)
                    ]

                    cid = on_chain_roots.get(root_key, {}).get("ipfs_cid") or meta.get("ipfs_cid", "")
                    gateway = on_chain_roots.get(root_key, {}).get("ipfs_gateway") or meta.get("ipfs_gateway", "")
                    match_info = {
                        "root": root_key,
                        "matched_filename": matched_filename,
                        "verified": is_valid,
                        "proof_steps": len(proof),
                        "proof": [{"hash": h, "direction": d} for h, d in proof],
                        "leaf_index": leaf_index,
                        "dataset_files": len(leaf_hashes),
                        "on_chain": root_key in on_chain_roots,
                        "dataset_version": on_chain_roots.get(root_key, {}).get("version", meta.get("version", "v1.0")),
                        "dataset_creator": on_chain_roots.get(root_key, {}).get("creator", meta.get("creator", "Unknown")),
                        "ipfs_cid": cid,
                        "ipfs_gateway": gateway,
                        "manifest_cid": meta.get("manifest_cid", ""),
                        "tree": tree_data,
                    }
                    if root_key in on_chain_roots:
                        match_info["record"] = on_chain_roots[root_key]
                    matches.append(match_info)
                except Exception:
                    pass

        # 2. Check any raw directories in UPLOAD_DIR not in registry
        if not matches and os.path.isdir(UPLOAD_DIR):
            for session_name in os.listdir(UPLOAD_DIR):
                session_dir = os.path.join(UPLOAD_DIR, session_name)
                if not os.path.isdir(session_dir):
                    continue
                try:
                    file_hashes_list = hash_dataset(session_dir)
                    if not file_hashes_list:
                        continue
                    leaf_hashes = [h for _, h in file_hashes_list]
                    leaf_index = None
                    matched_filename = None
                    for i, (rp, h) in enumerate(file_hashes_list):
                        if h == file_hash:
                            leaf_index = i
                            matched_filename = rp
                            break
                    if leaf_index is None:
                        continue
                    tree = build_tree(leaf_hashes)
                    root = get_root(tree)
                    proof = generate_proof(tree, leaf_index)
                    is_valid = verify_proof(file_hash, proof, root)

                    tree_data = [
                        {"level": idx, "nodes": [h[:16] + "..." for h in lvl]}
                        for idx, lvl in enumerate(tree)
                    ]
                    match_info = {
                        "root": root,
                        "matched_filename": matched_filename,
                        "verified": is_valid,
                        "proof_steps": len(proof),
                        "proof": [{"hash": h, "direction": d} for h, d in proof],
                        "leaf_index": leaf_index,
                        "dataset_files": len(file_hashes_list),
                        "on_chain": root in on_chain_roots,
                        "ipfs_cid": on_chain_roots.get(root, {}).get("ipfs_cid", ""),
                        "ipfs_gateway": on_chain_roots.get(root, {}).get("ipfs_gateway", ""),
                        "tree": tree_data,
                    }
                    if root in on_chain_roots:
                        match_info["record"] = on_chain_roots[root]
                        match_info["dataset_version"] = on_chain_roots[root]["version"]
                        match_info["dataset_creator"] = on_chain_roots[root]["creator"]
                    matches.append(match_info)
                except Exception:
                    continue

        if matches:
            on_chain_matches = [m for m in matches if m["on_chain"]]
            best = on_chain_matches[0] if on_chain_matches else matches[0]

            gw_domain = get_pinata_gateway()
            cid = best.get("ipfs_cid", "")
            matched_filename = best.get("matched_filename") or input_file_name
            file_ipfs_url = f"https://{gw_domain}/ipfs/{cid}/{matched_filename}" if cid and matched_filename else best.get("ipfs_gateway", "")

            return jsonify({
                "verified": best["verified"],
                "on_chain": best["on_chain"],
                "file_hash": file_hash,
                "file_name": input_file_name,
                "matched_name": matched_filename,
                "root": best["root"],
                "proof_steps": best["proof_steps"],
                "proof": best.get("proof", []),
                "leaf_index": best.get("leaf_index", 0),
                "dataset_files": best["dataset_files"],
                "dataset_version": best.get("dataset_version", "v1.0"),
                "dataset_creator": best.get("dataset_creator", "System Core"),
                "ipfs_cid": cid,
                "ipfs_url": file_ipfs_url,
                "ipfs_gateway": file_ipfs_url,
                "manifest_cid": best.get("manifest_cid", ""),
                "record": best.get("record"),
                "tree": best.get("tree"),
                "total_matches": len(matches),
                "unlocked_private_access": True,
                "message": (
                    "Cryptographic inclusion confirmed! Because you proved ownership of this record, your confidential decentralized IPFS file access has been unlocked."
                    if best["on_chain"] and best["verified"]
                    else "Record matches an audited dataset (pending on-chain anchoring)."
                    if best["verified"]
                    else "Record found but verification failed"
                ),
            })
        else:
            return jsonify({
                "verified": False,
                "on_chain": False,
                "file_hash": file_hash,
                "file_name": input_file_name,
                "total_matches": 0,
                "message": "Record not found in any audited on-chain dataset.",
            })

    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.unlink(temp_file_path)
            except Exception:
                pass


# ─── API: Get blockchain records ──────────────────────────────────────

@app.route("/api/records", methods=["GET"])
def api_records():
    """Read all audit records from the blockchain."""
    try:
        from web3 import Web3

        w3 = Web3(Web3.HTTPProvider("http://127.0.0.1:8545"))
        if not w3.is_connected():
            return jsonify({"error": "Blockchain node not running", "records": []}), 503

        # Load contract
        address_file = os.path.join(PROJECT_ROOT, "deployed_address.json")
        if not os.path.isfile(address_file):
            return jsonify({"error": "Contract not deployed", "records": []}), 503

        with open(address_file) as f:
            contract_address = json.load(f)["address"]

        abi_file = os.path.join(
            PROJECT_ROOT, "artifacts", "contracts", "AuditRegistry.sol", "AuditRegistry.json"
        )
        with open(abi_file) as f:
            contract_abi = json.load(f)["abi"]

        contract = w3.eth.contract(
            address=Web3.to_checksum_address(contract_address),
            abi=contract_abi,
        )

        auth_header = request.headers.get("Authorization", "")
        token = auth_header.replace("Bearer ", "").strip() if auth_header else ""
        is_company = token in active_sessions and active_sessions[token].get("role") == "company"

        reg = load_dataset_registry()
        gw_domain = get_pinata_gateway()
        count = contract.functions.getRecordCount().call()
        records = []

        for i in range(count):
            result = contract.functions.getRecord(i).call()
            root_hex = result[0].hex()
            reg_item = reg.get(root_hex, {})
            files_list = reg_item.get("files", [])

            rec = {
                "id": i,
                "root": root_hex,
                "version": result[1],
                "creator": result[2],
                "submitted_by": result[4],
                "timestamp": datetime.fromtimestamp(
                    result[5], tz=timezone.utc
                ).strftime("%Y-%m-%d %H:%M:%S UTC"),
            }

            if is_company:
                cid, gateway, manifest_cid = parse_notes_ipfs(result[3], root_hex)
                for f in files_list:
                    if not f.get("ipfs_url") and cid:
                        f["ipfs_url"] = f"https://{gw_domain}/ipfs/{cid}/{f['name']}"
                rec["notes"] = result[3]
                rec["ipfs_cid"] = cid
                rec["ipfs_gateway"] = gateway
                rec["manifest_cid"] = manifest_cid
                rec["file_count"] = reg_item.get("file_count", len(files_list) or 1)
                rec["files"] = files_list

            records.append(rec)

        return jsonify({"records": records, "count": count})

    except ImportError:
        return jsonify({"error": "web3 not installed", "records": []}), 503
    except Exception as e:
        return jsonify({"error": str(e), "records": []}), 500


# ─── API: Submit root to blockchain ───────────────────────────────────

@app.route("/api/submit-root", methods=["POST"])
def api_submit_root():
    """Submit a Merkle root to the blockchain with optional IPFS notes."""
    try:
        from web3 import Web3

        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON body"}), 400

        root_hex = data.get("root", "").strip()
        version = data.get("version", "v1.0").strip()
        creator = data.get("creator", "web-user").strip()
        account_index = data.get("account", 0)

        if not root_hex:
            return jsonify({"error": "No root hash provided"}), 400

        w3 = Web3(Web3.HTTPProvider("http://127.0.0.1:8545"))
        if not w3.is_connected():
            return jsonify({"error": "Blockchain node not running"}), 503

        # Load contract
        address_file = os.path.join(PROJECT_ROOT, "deployed_address.json")
        with open(address_file) as f:
            contract_address = json.load(f)["address"]

        abi_file = os.path.join(
            PROJECT_ROOT, "artifacts", "contracts", "AuditRegistry.sol", "AuditRegistry.json"
        )
        with open(abi_file) as f:
            contract_abi = json.load(f)["abi"]

        contract = w3.eth.contract(
            address=Web3.to_checksum_address(contract_address),
            abi=contract_abi,
        )

        account = w3.eth.accounts[account_index]
        root_bytes = bytes.fromhex(root_hex)

        # Check for duplicates
        already_exists = contract.functions.rootExists(root_bytes).call()
        if already_exists:
            return jsonify({"error": "Root already exists on-chain", "duplicate": True}), 409

        # Attach IPFS hybrid storage metadata in notes
        reg = load_dataset_registry()
        reg_item = reg.get(root_hex, {})
        ipfs_cid = data.get("ipfs_cid") or reg_item.get("ipfs_cid", "")
        ipfs_gateway = data.get("ipfs_gateway") or reg_item.get("ipfs_gateway", "")
        manifest_cid = reg_item.get("manifest_cid", "")

        notes_payload = {
            "ipfs_cid": ipfs_cid,
            "gateway": ipfs_gateway or (f"https://gateway.pinata.cloud/ipfs/{ipfs_cid}" if ipfs_cid else ""),
            "manifest_cid": manifest_cid,
        }
        notes_str = json.dumps(notes_payload) if ipfs_cid else data.get("notes", "")

        tx_hash = contract.functions.submitRootWithNotes(
            root_bytes, version, creator, notes_str
        ).transact({"from": account})

        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

        # Update persistent registry
        if root_hex in reg:
            reg[root_hex]["version"] = version
            reg[root_hex]["creator"] = creator
            reg[root_hex]["on_chain"] = True
            reg[root_hex]["tx_hash"] = receipt["transactionHash"].hex()
            reg[root_hex]["block_number"] = receipt["blockNumber"]
            save_dataset_registry(reg)

        return jsonify({
            "success": True,
            "tx_hash": receipt["transactionHash"].hex(),
            "block_number": receipt["blockNumber"],
            "root": root_hex,
            "version": version,
            "creator": creator,
            "ipfs_cid": ipfs_cid,
            "ipfs_gateway": notes_payload.get("gateway"),
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─── API: Public Overview & Decentralized Storage ─────────────────────

@app.route("/api/public-overview", methods=["GET"])
def api_public_overview():
    """
    Returns public blockchain audit ledger, active Merkle tree, and network stats.
    Powers the Public Decentralized Storage explorer.
    """
    records = []
    block_number = 0
    connected = False
    contract_address = None

    try:
        from web3 import Web3
        w3 = Web3(Web3.HTTPProvider("http://127.0.0.1:8545"))
        connected = w3.is_connected()
        if connected:
            block_number = w3.eth.block_number
            address_file = os.path.join(PROJECT_ROOT, "deployed_address.json")
            if os.path.isfile(address_file):
                with open(address_file) as f:
                    contract_address = json.load(f)["address"]
                abi_file = os.path.join(
                    PROJECT_ROOT, "artifacts", "contracts",
                    "AuditRegistry.sol", "AuditRegistry.json"
                )
                with open(abi_file) as f:
                    contract_abi = json.load(f)["abi"]
                contract = w3.eth.contract(
                    address=Web3.to_checksum_address(contract_address),
                    abi=contract_abi,
                )
                count = contract.functions.getRecordCount().call()
                reg_all = load_dataset_registry()
                gw_domain = get_pinata_gateway()
                for i in range(count):
                    result = contract.functions.getRecord(i).call()
                    root_hex = result[0].hex()
                    reg_item = reg_all.get(root_hex, {})
                    files_list = reg_item.get("files", [])

                    records.append({
                        "id": i,
                        "root": root_hex,
                        "version": result[1],
                        "creator": result[2],
                        "file_count": reg_item.get("file_count", len(files_list) or 1),
                        "submitted_by": result[4],
                        "timestamp": datetime.fromtimestamp(
                            result[5], tz=timezone.utc
                        ).strftime("%Y-%m-%d %H:%M:%S UTC"),
                        "privacy_status": "Confidential (Off-Chain)",
                    })
    except Exception as e:
        print(f"Notice: public overview blockchain query error: {e}")

    # Get registry and latest active tree
    reg = load_dataset_registry()
    latest_tree = None
    latest_root = None

    if records:
        latest_root = records[-1]["root"]
        if latest_root in reg:
            latest_tree = reg[latest_root].get("tree")
    elif reg:
        # Fallback to newest item in registry
        latest_item = list(reg.values())[-1]
        latest_root = latest_item.get("root")
        latest_tree = latest_item.get("tree")

    return jsonify({
        "blockchain_connected": connected,
        "contract_address": contract_address,
        "block_number": block_number,
        "records": records,
        "record_count": len(records),
        "total_datasets": len(reg),
        "latest_root": latest_root,
        "latest_tree": latest_tree,
        "latest_files": [],
        "privacy_shield": True,
        "ipfs_configured": is_pinata_configured(),
        "ipfs_gateway": get_pinata_gateway(),
    })


@app.route("/api/tree/<root_hex>", methods=["GET"])
def api_tree(root_hex):
    """Fetch tree structure and files for a specific Merkle root."""
    reg = load_dataset_registry()
    item = reg.get(root_hex)
    if not item:
        return jsonify({"error": "Dataset tree not found in registry"}), 404

    auth_header = request.headers.get("Authorization", "")
    token = auth_header.replace("Bearer ", "").strip() if auth_header else ""
    is_company = token in active_sessions and active_sessions[token].get("role") == "company"

    gw_domain = get_pinata_gateway()
    cid = item.get("ipfs_cid", "")
    files = item.get("files", [])
    for f in files:
        if not f.get("ipfs_url") and cid:
            f["ipfs_url"] = f"https://{gw_domain}/ipfs/{cid}/{f['name']}"

    return jsonify({
        "root": item.get("root"),
        "version": item.get("version"),
        "creator": item.get("creator"),
        "file_count": item.get("file_count"),
        "files": files if is_company else [],
        "tree": item.get("tree"),
        "ipfs_cid": item.get("ipfs_cid") if is_company else None,
        "ipfs_gateway": item.get("ipfs_gateway") if is_company else None,
        "manifest_cid": item.get("manifest_cid") if is_company else None,
        "timestamp": item.get("timestamp"),
        "privacy_status": "Confidential (Off-Chain)" if not is_company else "Admin Access",
    })


# ─── API: IPFS Status & Configuration ─────────────────────────────────

@app.route("/api/ipfs-status", methods=["GET"])
def api_ipfs_status():
    """Returns Pinata IPFS integration status, auth status, gateway, and mode."""
    auth_res = test_pinata_auth()
    return jsonify({
        "configured": is_pinata_configured(),
        "mode": auth_res.get("mode"),
        "authenticated": auth_res.get("authenticated"),
        "message": auth_res.get("message"),
        "gateway": get_pinata_gateway(),
    })


@app.route("/api/ipfs-config", methods=["POST"])
def api_ipfs_config():
    """Update Pinata JWT and Gateway in .env."""
    data = request.get_json() or {}
    jwt = data.get("jwt", "").strip()
    gateway = data.get("gateway", "").strip() or "gateway.pinata.cloud"

    if not jwt:
        return jsonify({"error": "JWT cannot be empty"}), 400

    lines = []
    if os.path.isfile(ENV_FILE):
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()

    updated_jwt = False
    updated_gw = False
    new_lines = []
    for line in lines:
        if line.startswith("PINATA_JWT="):
            new_lines.append(f'PINATA_JWT="{jwt}"\n')
            updated_jwt = True
        elif line.startswith("PINATA_GATEWAY="):
            new_lines.append(f'PINATA_GATEWAY="{gateway}"\n')
            updated_gw = True
        else:
            new_lines.append(line)

    if not updated_jwt:
        new_lines.append(f'PINATA_JWT="{jwt}"\n')
    if not updated_gw:
        new_lines.append(f'PINATA_GATEWAY="{gateway}"\n')

    with open(ENV_FILE, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

    os.environ["PINATA_JWT"] = jwt
    os.environ["PINATA_GATEWAY"] = gateway

    auth_res = test_pinata_auth()
    return jsonify({
        "success": True,
        "authenticated": auth_res.get("authenticated"),
        "mode": auth_res.get("mode"),
        "message": auth_res.get("message"),
        "gateway": gateway,
    })


# ─── API: Health check ────────────────────────────────────────────────

@app.route("/api/health", methods=["GET"])
def api_health():
    """Check if blockchain node is reachable with extended info."""
    connected = False
    block_number = 0
    count = 0
    contract_address = None

    try:
        from web3 import Web3
        w3 = Web3(Web3.HTTPProvider("http://127.0.0.1:8545"))
        connected = w3.is_connected()
        if connected:
            block_number = w3.eth.block_number
            address_file = os.path.join(PROJECT_ROOT, "deployed_address.json")
            if os.path.isfile(address_file):
                with open(address_file) as f:
                    contract_address = json.load(f)["address"]
                abi_file = os.path.join(
                    PROJECT_ROOT, "artifacts", "contracts",
                    "AuditRegistry.sol", "AuditRegistry.json"
                )
                with open(abi_file) as f:
                    contract_abi = json.load(f)["abi"]
                contract = w3.eth.contract(
                    address=Web3.to_checksum_address(contract_address),
                    abi=contract_abi,
                )
                count = contract.functions.getRecordCount().call()
    except Exception:
        pass

    return jsonify({
        "server": True,
        "blockchain": connected,
        "contract_deployed": contract_address is not None,
        "contract_address": contract_address,
        "block_number": block_number,
        "record_count": count,
    })


# ─── Main ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"Serving frontend from: {FRONTEND_DIR}")
    print(f"Project root: {PROJECT_ROOT}")
    print("Starting Merkle Root server on http://localhost:5000")
    app.run(host="0.0.0.0", port=5000, debug=False)
