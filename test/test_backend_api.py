import os
import sys
import json
import io
import time
import hashlib
from datetime import datetime

# Add python dir to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))
from server import app, load_dataset_registry, get_contract

def run_tests():
    client = app.test_client()

    print("=== TEST 1: Health Check ===")
    res = client.get("/api/health")
    assert res.status_code == 200, f"Health check failed: {res.data}"
    health_data = res.get_json()
    print(f"Health: blockchain={health_data.get('blockchain')}, contract_deployed={health_data.get('contract_deployed')}")
    assert health_data.get("blockchain") is True, "Blockchain not connected!"
    assert health_data.get("contract_deployed") is True, "Contract not deployed!"

    print("\n=== TEST 2: Hash Dataset with Parallel Streaming & Nutrition Label ===")
    ts = datetime.now().timestamp()
    file1_content = f"Run {ts} Patient 101: Blood test normal, glucose 95 mg/dL. Confidential medical record.\n".encode()
    file2_content = f"Run {ts} Patient 102: MRI brain scan normal, no acute intracranial hemorrhage detected.\n".encode()
    file3_content = f"Run {ts} Patient 103: ECG sinus rhythm 72 bpm, no ST elevation or ischemia noted.\n".encode()

    data = {
        "files": [
            (io.BytesIO(file1_content), "patient_101.txt"),
            (io.BytesIO(file2_content), "patient_102.txt"),
            (io.BytesIO(file3_content), "patient_103.txt"),
        ]
    }
    res = client.post("/api/hash-dataset", data=data, content_type="multipart/form-data")
    assert res.status_code == 200, f"Hash dataset failed: {res.data}"
    hash_data = res.get_json()
    root_v1 = hash_data["root"]
    print(f"Dataset v1 root: {root_v1}")
    assert "telemetry" in hash_data, "Telemetry missing!"
    print(f"Telemetry: {hash_data['telemetry']}")
    assert "nutrition_label" in hash_data, "Nutrition label missing!"
    print(f"Nutrition Label: {hash_data['nutrition_label']}")
    assert len(hash_data["files"]) == 3, f"Expected 3 files, got {len(hash_data['files'])}"
    assert hash_data["files"][0].get("fingerprint") is not None, "Fingerprint missing!"

    print("\n=== TEST 3: Submit Root v1 to Blockchain ===")
    res = client.post("/api/submit-root", json={
        "root": root_v1,
        "version": "v1.0-genesis",
        "creator": "Hospital Core Alpha",
        "account": 0,
    })
    assert res.status_code == 200, f"Submit root failed: {res.data}"
    sub_data = res.get_json()
    print(f"Anchored in block {sub_data['block_number']}, tx: {sub_data['tx_hash'][:18]}...")

    print("\n=== TEST 4: Triple-Layer Verification (Exact Match) ===")
    res = client.post("/api/verify", data={
        "file": (io.BytesIO(file1_content), "patient_101.txt")
    }, content_type="multipart/form-data")
    assert res.status_code == 200, f"Verify failed: {res.data}"
    v_data = res.get_json()
    print(f"Verify exact match status: {v_data.get('status')}")
    print(f"  offchain_verified: {v_data.get('offchain_verified')}")
    print(f"  onchain_verified:  {v_data.get('onchain_verified')}")
    print(f"  unlocked_private_access: {v_data.get('unlocked_private_access')}")
    assert v_data.get("verified") is True, "Expected verified=True"
    assert v_data.get("onchain_verified") is True, "Expected onchain_verified=True"
    assert v_data.get("unlocked_private_access") is True, "Expected private access unlocked"

    print("\n=== TEST 5: Fuzzy / Perceptual IP Fallback (Near-Match Tamper Detection) ===")
    # Modify one word in patient 101: "normal" -> "normalll"
    modified_content = f"Run {ts} Patient 101: Blood test normalll, glucose 95 mg/dL. Confidential medical record.\n".encode()
    res = client.post("/api/verify", data={
        "file": (io.BytesIO(modified_content), "patient_101_tampered.txt")
    }, content_type="multipart/form-data")
    assert res.status_code == 200, f"Verify near match failed: {res.data}"
    v_fuzzy = res.get_json()
    print(f"Fuzzy verify status: {v_fuzzy.get('status')}")
    print(f"  fuzzy_matched:    {v_fuzzy.get('fuzzy_matched')}")
    print(f"  similarity_score: {v_fuzzy.get('similarity_score')}%")
    print(f"  unlocked_private_access: {v_fuzzy.get('unlocked_private_access')}")
    print(f"  message: {v_fuzzy.get('message')}")
    assert v_fuzzy.get("status") == "NEAR_MATCH_DETECTED", "Expected NEAR_MATCH_DETECTED"
    assert v_fuzzy.get("similarity_score") >= 80.0, "Expected >=80% similarity"
    assert v_fuzzy.get("unlocked_private_access") is False, "Private access MUST stay locked on near match!"

    print("\n=== TEST 6: Register AI Model Checkpoint Provenance ===")
    model_weights_hash = hashlib.sha256(f"model-{ts}".encode()).hexdigest()
    res = client.post("/api/register-model", json={
        "model_hash": model_weights_hash,
        "dataset_root": root_v1,
        "model_name": "MedDiag-BioBERT-v1",
        "framework": "PyTorch / HuggingFace",
        "metrics": {"auc": 0.984, "f1": 0.962, "accuracy": 0.978},
        "account": 0,
    })
    assert res.status_code == 200, f"Register model failed: {res.data}"
    m_reg_data = res.get_json()
    print(f"Model registered: {m_reg_data['model']['model_name']} -> tx: {m_reg_data['tx_hash'][:18]}...")

    res = client.get("/api/models")
    assert res.status_code == 200
    models_res = res.get_json()
    print(f"Total AI models on-chain: {models_res['count']}")
    assert models_res["count"] >= 1, "Expected at least 1 registered model"

    print("\n=== TEST 7: Dataset Superseding (Poisoned Data Purge & Lineage) ===")
    # v2 dataset: patient 102 removed (GDPR deletion), patient 104 added
    file4_content = f"Run {ts} Patient 104: Ultrasound thyroid normal, benign colloid nodule 4mm.\n".encode()
    data_v2 = {
        "files": [
            (io.BytesIO(file1_content), "patient_101.txt"),
            (io.BytesIO(file3_content), "patient_103.txt"),
            (io.BytesIO(file4_content), "patient_104.txt"),
        ]
    }
    res = client.post("/api/hash-dataset", data=data_v2, content_type="multipart/form-data")
    assert res.status_code == 200
    root_v2 = res.get_json()["root"]
    print(f"Dataset v2 root: {root_v2}")

    # Supersede v1 with v2
    res = client.post("/api/submit-root", json={
        "root": root_v2,
        "version": "v2.0-clean",
        "creator": "Hospital Core Alpha",
        "parent_root": root_v1,
        "revocation_reason": "GDPR Right-to-be-Forgotten request: Patient 102 purged",
        "account": 0,
    })
    assert res.status_code == 200, f"Supersede failed: {res.data}"
    sup_data = res.get_json()
    print(f"Superseded root v1 with v2 on-chain! is_supersede={sup_data['is_supersede']}")
    assert sup_data["is_supersede"] is True

    print("\n=== TEST 8: Zero-Knowledge Leaf Diff ===")
    res = client.get(f"/api/diff/{root_v1}/{root_v2}")
    assert res.status_code == 200, f"Diff failed: {res.data}"
    diff_data = res.get_json()["diff"]
    print(f"Diff results: retained={diff_data['retained_count']}, tombstoned={diff_data['tombstoned_count']}, added={diff_data['added_count']}")
    assert diff_data["tombstoned_count"] == 1, f"Expected 1 tombstoned leaf, got {diff_data['tombstoned_count']}"
    assert diff_data["added_count"] == 1, f"Expected 1 added leaf, got {diff_data['added_count']}"
    assert diff_data["retained_count"] == 2, f"Expected 2 retained leaves, got {diff_data['retained_count']}"

    print("\n=== TEST 9: Compliance Audit Certificate ===")
    # Certificate JSON
    p101_hash = hash_data["files"][0]["full_hash"]
    res = client.post("/api/certificate", json={
        "file_hash": p101_hash,
        "root": root_v1,
        "file_name": "patient_101.txt",
        "format": "json",
    })
    assert res.status_code == 200, f"Certificate JSON failed: {res.data}"
    cert = res.get_json()
    print(f"Generated Certificate: {cert['certificate_id']}")
    print(f"  Seal Signature: {cert['digital_signature'][:24]}...")
    assert cert["status"] == "AUTHENTICATED_AND_ANCHORED"

    # Certificate HTML
    res_html = client.post("/api/certificate", json={
        "file_hash": p101_hash,
        "root": root_v1,
        "file_name": "patient_101.txt",
        "format": "html",
    })
    assert res_html.status_code == 200
    assert b"CRYPTOGRAPHIC AUDIT CERTIFICATE" in res_html.data
    print("Certificate HTML generated cleanly!")

    print("\n=== TEST 10: Public Overview (Privacy & Lineage Check) ===")
    res = client.get("/api/public-overview")
    assert res.status_code == 200
    pub = res.get_json()
    print(f"Public records count: {pub['record_count']}, models count: {pub['model_count']}")
    assert pub["record_count"] >= 2, "Expected at least 2 records"
    assert len(pub["latest_files"]) == 0, "Confidentiality violated! Public latest_files must be empty!"
    # Verify lineage for root_v1 (which was superseded)
    rec_v1 = next(r for r in pub["records"] if r["root"] == root_v1)
    print(f"Record root_v1 {rec_v1['root'][:16]}...: is_revoked={rec_v1['is_revoked']}, superseded_by={rec_v1['superseded_by'][:16] if rec_v1['superseded_by'] else None}, reason={rec_v1['revocation_reason']}")
    assert rec_v1["is_revoked"] is True, "Root v1 must show is_revoked=True"
    assert rec_v1["superseded_by"] == root_v2, "Root v1 superseded_by must equal root_v2"

    print("\n=== TEST 11: Multi-Actor Wallets & Balances ===")
    res = client.get("/api/wallets")
    assert res.status_code == 200
    w_data = res.get_json()
    assert len(w_data["wallets"]) == 4, f"Expected 4 wallets, got {len(w_data['wallets'])}"
    print(f"Wallets retrieved: {[w['name'] + ' (' + str(w['balance_eth']) + ' ETH)' for w in w_data['wallets']]}")

    print("\n=== TEST 12: Public Zero-Knowledge Tree Manifest ===")
    res = client.get(f"/api/zk-manifest/{root_v2}")
    assert res.status_code == 200
    zk_man = res.get_json()
    assert zk_man["root"] == root_v2
    assert "tree_levels" in zk_man
    assert "leaf_hashes" in zk_man
    # Ensure zero filenames leaked
    assert "files" not in zk_man
    print(f"ZK Manifest verified for {root_v2[:16]}... (Levels: {len(zk_man['tree_levels'])}, Leaves: {len(zk_man['leaf_hashes'])})")

    print("\n=== TEST 13: Staked Dataset Submission & Auditor Attestation ===")
    unique_staked_root = hashlib.sha256(f"staked_dataset_pool_{time.time()}".encode()).hexdigest()
    # Submit staked dataset with Account #1 (Company)
    res = client.post("/api/submit-root", json={
        "root": unique_staked_root,
        "version": "v1.0-staked-pool",
        "creator": "Hospital Alpha Corp",
        "auditor_fee_eth": 0.2,
        "collateral_bond_eth": 1.0,
        "account": 1,
    })
    assert res.status_code == 200, f"Submit staked root failed: {res.data}"
    staked_root = unique_staked_root

    # Verify company CANNOT self-attest
    res = client.post("/api/attest-dataset", json={
        "root": staked_root,
        "account": 1, # Company submitter
    })
    assert res.status_code == 403, f"Company self-attest must be rejected with 403! Got {res.status_code}"
    print("Confirmed: Company self-attestation strictly rejected (Separation of Powers enforced)")

    # Attest with Account #2 (EU Regulator)
    res = client.post("/api/attest-dataset", json={
        "root": staked_root,
        "account": 2, # Authorized Auditor
        "audit_report_uri": "ipfs://audit-report-eureg-001",
    })
    assert res.status_code == 200
    attest_data = res.get_json()
    assert attest_data["status"] == "AUDITOR_ATTESTED"
    print(f"Dataset successfully attested by Regulator: {attest_data['attested_by']} (Reputation: {attest_data['auditor_reputation']})")

    print("\n=== TEST 14: Creator IP Registration & Scanner ===")
    res = client.post("/api/creator-ip", json={
        "title": "Novel CRISPR Genome Sequence Analysis",
        "exact_hash": p101_hash, # This was in dataset root_v1
        "simhash": "0x1234567890abcdef",
        "license_fee_eth": 0.05,
        "account": 3,
    })
    assert res.status_code == 200
    cip_data = res.get_json()
    print(f"Creator IP registered on-chain: '{cip_data['title']}' (Price: {cip_data['license_fee_eth']} ETH)")

    res = client.get("/api/creator-ip")
    assert res.status_code == 200
    works_data = res.get_json()
    assert works_data["count"] >= 1
    print(f"Total creator works on-chain: {works_data['count']}")

    print("\n=== TEST 15: TEE Hardware Enclave Attestation Model Binding ===")
    tee_quote = "0x8888888888888888888888888888888888888888888888888888888888888888"
    canary = "0x9999999999999999999999999999999999999999999999999999999999999999"
    unique_model_hash = hashlib.sha256(f"sgx_model_{time.time()}".encode()).hexdigest()
    res = client.post("/api/register-model", json={
        "model_hash": unique_model_hash,
        "dataset_root": staked_root,
        "model_name": "SGX-BioMed-Classifier",
        "framework": "PyTorch / Intel SGX Enclave",
        "metrics": {"f1": 0.991, "enclave_verified": True},
        "tee_enclave_quote_hash": tee_quote,
        "canary_trap_hash": canary,
        "account": 1,
    })
    assert res.status_code == 200
    m_res = res.get_json()["model"]
    assert m_res["is_tee_secured"] is True
    print(f"TEE Model checkpoint bound: {m_res['model_name']} (TEE Secured: {m_res['is_tee_secured']})")

    print("\nALL 15 BACKEND & PROTOCOL INTEGRATION TESTS PASSED PERFECTLY!")

if __name__ == "__main__":
    run_tests()
