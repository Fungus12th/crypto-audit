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

# ─── App setup ────────────────────────────────────────────────────────

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
FRONTEND_DIR = os.path.join(PROJECT_ROOT, "frontend")
UPLOAD_DIR = os.path.join(PROJECT_ROOT, "uploads")
REGISTRY_FILE = os.path.join(PROJECT_ROOT, "dataset_registry.json")
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = Flask(__name__, static_folder=FRONTEND_DIR)
CORS(app)


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
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400

    # Save the uploaded file temporarily
    temp_file = tempfile.NamedTemporaryFile(dir=UPLOAD_DIR, delete=False)
    try:
        file.save(temp_file.name)
        file_hash = hash_file(temp_file.name)

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
                        on_chain_roots[root_hex] = {
                            "id": i,
                            "version": result[1],
                            "creator": result[2],
                            "notes": result[3],
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

            return jsonify({
                "verified": best["verified"],
                "on_chain": best["on_chain"],
                "file_hash": file_hash,
                "file_name": file.filename,
                "matched_name": best.get("matched_filename") or file.filename,
                "root": best["root"],
                "proof_steps": best["proof_steps"],
                "proof": best.get("proof", []),
                "leaf_index": best.get("leaf_index", 0),
                "dataset_files": best["dataset_files"],
                "dataset_version": best.get("dataset_version", "v1.0"),
                "dataset_creator": best.get("dataset_creator", "System Core"),
                "record": best.get("record"),
                "tree": best.get("tree"),
                "total_matches": len(matches),
                "message": (
                    "File is cryptographically verified and anchored on the blockchain!"
                    if best["on_chain"] and best["verified"]
                    else "File matches an audited dataset (pending on-chain anchoring)."
                    if best["verified"]
                    else "File found but verification failed"
                ),
            })
        else:
            return jsonify({
                "verified": False,
                "on_chain": False,
                "file_hash": file_hash,
                "file_name": file.filename,
                "total_matches": 0,
                "message": "File not found in any audited dataset.",
            })

    finally:
        os.unlink(temp_file.name)


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

        count = contract.functions.getRecordCount().call()
        records = []

        for i in range(count):
            result = contract.functions.getRecord(i).call()
            records.append({
                "id": i,
                "root": result[0].hex(),
                "version": result[1],
                "creator": result[2],
                "notes": result[3],
                "submitted_by": result[4],
                "timestamp": datetime.fromtimestamp(
                    result[5], tz=timezone.utc
                ).strftime("%Y-%m-%d %H:%M:%S UTC"),
            })

        return jsonify({"records": records, "count": count})

    except ImportError:
        return jsonify({"error": "web3 not installed", "records": []}), 503
    except Exception as e:
        return jsonify({"error": str(e), "records": []}), 500


# ─── API: Submit root to blockchain ───────────────────────────────────

@app.route("/api/submit-root", methods=["POST"])
def api_submit_root():
    """Submit a Merkle root to the blockchain."""
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

        tx_hash = contract.functions.submitRoot(
            root_bytes, version, creator
        ).transact({"from": account})

        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

        # Update persistent registry
        reg = load_dataset_registry()
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
                for i in range(count):
                    result = contract.functions.getRecord(i).call()
                    records.append({
                        "id": i,
                        "root": result[0].hex(),
                        "version": result[1],
                        "creator": result[2],
                        "notes": result[3],
                        "submitted_by": result[4],
                        "timestamp": datetime.fromtimestamp(
                            result[5], tz=timezone.utc
                        ).strftime("%Y-%m-%d %H:%M:%S UTC"),
                    })
    except Exception as e:
        print(f"Notice: public overview blockchain query error: {e}")

    # Get registry and latest active tree
    reg = load_dataset_registry()
    latest_tree = None
    latest_root = None
    latest_files = []

    if records:
        latest_root = records[-1]["root"]
        if latest_root in reg:
            latest_tree = reg[latest_root].get("tree")
            latest_files = reg[latest_root].get("files", [])
    elif reg:
        # Fallback to newest item in registry
        latest_item = list(reg.values())[-1]
        latest_root = latest_item.get("root")
        latest_tree = latest_item.get("tree")
        latest_files = latest_item.get("files", [])

    return jsonify({
        "blockchain_connected": connected,
        "contract_address": contract_address,
        "block_number": block_number,
        "records": records,
        "record_count": len(records),
        "total_datasets": len(reg),
        "latest_root": latest_root,
        "latest_tree": latest_tree,
        "latest_files": latest_files,
    })


@app.route("/api/tree/<root_hex>", methods=["GET"])
def api_tree(root_hex):
    """Fetch tree structure and files for a specific Merkle root."""
    reg = load_dataset_registry()
    item = reg.get(root_hex)
    if not item:
        return jsonify({"error": "Dataset tree not found in registry"}), 404
    return jsonify({
        "root": item.get("root"),
        "version": item.get("version"),
        "creator": item.get("creator"),
        "file_count": item.get("file_count"),
        "files": item.get("files", []),
        "tree": item.get("tree"),
        "timestamp": item.get("timestamp"),
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
