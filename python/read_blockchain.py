"""
read_blockchain.py — Read all stored audit records from the blockchain
=====================================================================
This script connects to the local Hardhat node and reads every
audit record that has been submitted to the AuditRegistry contract.

Usage:
  python3 python/read_blockchain.py

Think of this as "opening the vault and looking at what's inside."
"""

import json
import os
import sys

from web3 import Web3


def main():
    # Connect to Hardhat node
    project_root = os.path.join(os.path.dirname(__file__), "..")
    w3 = Web3(Web3.HTTPProvider("http://127.0.0.1:8545"))

    if not w3.is_connected():
        print("❌ Hardhat node not running. Start it with: npx hardhat node")
        sys.exit(1)

    # Load contract
    address_file = os.path.join(project_root, "deployed_address.json")
    if not os.path.isfile(address_file):
        print("❌ No deployed_address.json. Deploy first with:")
        print("   npx hardhat run scripts/deploy.js --network localhost")
        sys.exit(1)

    with open(address_file) as f:
        contract_address = json.load(f)["address"]

    abi_file = os.path.join(
        project_root,
        "artifacts", "contracts", "AuditRegistry.sol", "AuditRegistry.json"
    )
    with open(abi_file) as f:
        contract_abi = json.load(f)["abi"]

    contract = w3.eth.contract(
        address=Web3.to_checksum_address(contract_address),
        abi=contract_abi
    )

    print("\n🔍 Reading all records from the blockchain...")
    print(f"   Contract address: {contract_address}")
    print("=" * 65)

    # Try reading records starting from ID 0
    record_id = 0
    found_any = False

    while True:
        try:
            result = contract.functions.getRoot(record_id).call()
            found_any = True

            root_hex = result[0].hex()
            version = result[1]
            creator = result[2]
            timestamp = result[3]

            print(f"\n   📦 Record #{record_id}")
            print(f"      Merkle Root:  {root_hex}")
            print(f"      Version:      {version}")
            print(f"      Creator:      {creator}")
            print(f"      Timestamp:    {timestamp}")
            print(f"      ─────────────────────────────────")

            record_id += 1
        except Exception:
            # No more records — array index out of bounds
            break

    if not found_any:
        print("\n   📭 No records found. Submit a root first with:")
        print("      python3 python/submit_root.py")
    else:
        print(f"\n   ✅ Found {record_id} record(s) on the blockchain.")
        print("   These are PERMANENT — nobody can edit or delete them.\n")


if __name__ == "__main__":
    main()
