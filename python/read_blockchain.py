import json
import os
import sys

from web3 import Web3


def main():
    project_root = os.path.join(os.path.dirname(__file__), "..")
    w3 = Web3(Web3.HTTPProvider("http://127.0.0.1:8545"))

    if not w3.is_connected():
        print("Error: Hardhat node not running. Start it with: npx hardhat node")
        sys.exit(1)

    # Load contract
    address_file = os.path.join(project_root, "deployed_address.json")
    if not os.path.isfile(address_file):
        print("Error: No deployed_address.json found. Deploy first with:")
        print("npx hardhat run scripts/deploy.js --network localhost")
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

    print(f"Reading records from {contract_address}...\n")

    count = contract.functions.getRecordCount().call()

    if count == 0:
        print("No records found. Submit a root first with:")
        print("python python/submit_root.py")
        return

    for record_id in range(count):
        result = contract.functions.getRecord(record_id).call()

        root_hex = result[0].hex()
        version = result[1]
        creator = result[2]
        notes = result[3]
        submitted_by = result[4]
        timestamp = result[5]

        print(f"Record #{record_id}")
        print(f"  Merkle Root:   {root_hex}")
        print(f"  Version:       {version}")
        print(f"  Creator:       {creator}")
        if notes:
            print(f"  Notes:         {notes}")
        print(f"  Submitted By:  {submitted_by}")
        print(f"  Timestamp:     {timestamp}\n")

    print(f"Found {count} record(s) on the blockchain.")


if __name__ == "__main__":
    main()
