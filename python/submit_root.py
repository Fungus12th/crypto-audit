"""
submit_root.py — Bridge between Python Merkle Engine and Blockchain
====================================================================
This script:
  1. Hashes the dataset using our Merkle engine → gets the Merkle root
  2. Connects to the local Hardhat node via web3.py
  3. Loads the deployed AuditRegistry contract
  4. Calls submitRoot() to store the root on-chain
  5. Calls getRoot() to read it back and confirm it matches

Usage:
  1. Start Hardhat node:   npx hardhat node
  2. Deploy contract:      npx hardhat run scripts/deploy.js --network localhost
  3. Run this script:      python python/submit_root.py
"""

import json
import os
import sys

from web3 import Web3

# Import our Merkle engine
from merkle import hash_dataset, build_tree, get_root


def main():
    # ------------------------------------------------------------------
    # STEP 1: Compute the Merkle root from the local dataset
    # ------------------------------------------------------------------
    project_root = os.path.join(os.path.dirname(__file__), "..")
    data_folder = os.path.join(project_root, "data")

    print("\n📂 Hashing dataset...")
    file_hashes = hash_dataset(data_folder)
    leaf_hashes = [h for _, h in file_hashes]
    tree = build_tree(leaf_hashes)
    merkle_root = get_root(tree)

    print(f"   Merkle root: {merkle_root}")

    # ------------------------------------------------------------------
    # STEP 2: Connect to the local Hardhat node
    # ------------------------------------------------------------------
    rpc_url = "http://127.0.0.1:8545"
    w3 = Web3(Web3.HTTPProvider(rpc_url))

    if not w3.is_connected():
        print(f"❌ Cannot connect to Hardhat node at {rpc_url}")
        print("   Make sure you've started it with: npx hardhat node")
        sys.exit(1)

    print(f"✅ Connected to Hardhat node at {rpc_url}")

    # Use the first Hardhat test account (pre-funded with 10000 ETH)
    account = w3.eth.accounts[0]
    print(f"   Using account: {account}")

    # ------------------------------------------------------------------
    # STEP 3: Load the deployed contract
    # ------------------------------------------------------------------
    # Read the contract address (saved by deploy.js)
    address_file = os.path.join(project_root, "deployed_address.json")
    if not os.path.isfile(address_file):
        print(f"❌ Cannot find {address_file}")
        print("   Deploy the contract first with:")
        print("   npx hardhat run scripts/deploy.js --network localhost")
        sys.exit(1)

    with open(address_file) as f:
        contract_address = json.load(f)["address"]

    # Read the contract ABI from Hardhat's compiled artifacts
    abi_file = os.path.join(
        project_root,
        "artifacts", "contracts", "AuditRegistry.sol", "AuditRegistry.json"
    )
    if not os.path.isfile(abi_file):
        print(f"❌ Cannot find ABI file at {abi_file}")
        print("   Compile the contract first with: npx hardhat compile")
        sys.exit(1)

    with open(abi_file) as f:
        contract_abi = json.load(f)["abi"]

    # Create the contract object
    contract = w3.eth.contract(
        address=Web3.to_checksum_address(contract_address),
        abi=contract_abi
    )
    print(f"📄 Loaded AuditRegistry at {contract_address}")

    # ------------------------------------------------------------------
    # STEP 4: Submit the Merkle root on-chain
    # ------------------------------------------------------------------
    # Convert the 64-char hex string to bytes32 (left-pad with 0x)
    root_bytes32 = bytes.fromhex(merkle_root)

    dataset_version = "v1.0"
    creator = "demo-user"

    print(f"\n📤 Submitting root to blockchain...")
    print(f"   Version: {dataset_version}")
    print(f"   Creator: {creator}")

    # Build and send the transaction
    tx_hash = contract.functions.submitRoot(
        root_bytes32, dataset_version, creator
    ).transact({"from": account})

    # Wait for the transaction to be mined
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    print(f"   ✅ Transaction mined in block {receipt['blockNumber']}")

    # ------------------------------------------------------------------
    # STEP 5: Read the root back and verify it matches
    # ------------------------------------------------------------------
    print(f"\n📥 Reading root back from blockchain...")

    # getRoot(0) returns (root, datasetVersion, creator, timestamp)
    result = contract.functions.getRoot(0).call()

    on_chain_root = result[0].hex()  # Convert bytes32 back to hex string
    on_chain_version = result[1]
    on_chain_creator = result[2]
    on_chain_timestamp = result[3]

    print(f"   On-chain root:    {on_chain_root}")
    print(f"   On-chain version: {on_chain_version}")
    print(f"   On-chain creator: {on_chain_creator}")
    print(f"   On-chain time:    {on_chain_timestamp}")

    # Verify the match
    if on_chain_root == merkle_root:
        print(f"\n🎉 SUCCESS — On-chain root matches local Merkle root!")
    else:
        print(f"\n❌ MISMATCH!")
        print(f"   Local root:    {merkle_root}")
        print(f"   On-chain root: {on_chain_root}")
        sys.exit(1)

    print()


if __name__ == "__main__":
    main()
