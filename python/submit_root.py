import argparse
from datetime import datetime, timezone
import json
import os
import sys

from web3 import Web3
from merkle import hash_dataset, build_tree, get_root


def load_contract(w3, project_root):
    """Load the deployed AuditRegistry contract."""
    address_file = os.path.join(project_root, "deployed_address.json")
    if not os.path.isfile(address_file):
        print(f"Error: Cannot find {address_file}")
        print("Deploy the contract first with:")
        print("  npx hardhat run scripts/deploy.js --network localhost")
        sys.exit(1)

    with open(address_file) as f:
        contract_address = json.load(f)["address"]

    abi_file = os.path.join(
        project_root,
        "artifacts", "contracts", "AuditRegistry.sol", "AuditRegistry.json"
    )
    if not os.path.isfile(abi_file):
        print(f"Error: Cannot find ABI file at {abi_file}")
        print("Compile the contract first with: npx hardhat compile")
        sys.exit(1)

    with open(abi_file) as f:
        contract_abi = json.load(f)["abi"]

    contract = w3.eth.contract(
        address=Web3.to_checksum_address(contract_address),
        abi=contract_abi
    )
    return contract, contract_address


def main():
    parser = argparse.ArgumentParser(description="Submit dataset Merkle root to the blockchain")
    parser.add_argument("folder", nargs="?", default=None, help="Dataset directory (default: ./data)")
    parser.add_argument("--version", default="v1.0", help="Dataset version label (default: v1.0)")
    parser.add_argument("--creator", default="demo-user", help="Creator name (default: demo-user)")
    parser.add_argument("--account", type=int, default=0, help="Account index to use (default: 0)")
    args = parser.parse_args()

    project_root = os.path.join(os.path.dirname(__file__), "..")
    data_folder = args.folder if args.folder else os.path.join(project_root, "data")

    # Hash the dataset
    print("Hashing dataset...")
    file_hashes = hash_dataset(data_folder)
    leaf_hashes = [h for _, h in file_hashes]
    tree = build_tree(leaf_hashes)
    merkle_root = get_root(tree)

    print(f"Merkle root: {merkle_root}")

    # Connect to local node
    rpc_url = "http://127.0.0.1:8545"
    w3 = Web3(Web3.HTTPProvider(rpc_url))

    if not w3.is_connected():
        print(f"Error: Cannot connect to node at {rpc_url}")
        print("Make sure you've started it with: npx hardhat node")
        sys.exit(1)

    print(f"Connected to node at {rpc_url}")

    account = w3.eth.accounts[args.account]
    print(f"Using account: {account}")

    # Load contract
    contract, contract_address = load_contract(w3, project_root)
    print(f"Loaded AuditRegistry at {contract_address}")

    # Check if root already exists on-chain before attempting to submit
    root_bytes32 = bytes.fromhex(merkle_root)
    already_exists = contract.functions.rootExists(root_bytes32).call()

    if already_exists:
        print(f"\nRoot already exists on-chain: {merkle_root}")
        print("The dataset has not changed since the last submission.")
        print("Modify the dataset or use a different version to submit a new root.")

        # Show the existing record for reference
        count = contract.functions.getRecordCount().call()
        for i in range(count):
            result = contract.functions.getRecord(i).call()
            if result[0].hex() == merkle_root:
                print(f"\nExisting record #{i}:")
                print(f"  Version:      {result[1]}")
                print(f"  Creator:      {result[2]}")
                print(f"  Submitted by: {result[4]}")
                print(f"  Timestamp:    {datetime.fromtimestamp(result[5], tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
                break
        return

    # Submit root on-chain
    dataset_version = args.version
    creator = args.creator

    print(f"\nSubmitting root to blockchain...")
    print(f"Version: {dataset_version}")
    print(f"Creator: {creator}")

    tx_hash = contract.functions.submitRoot(
        root_bytes32, dataset_version, creator
    ).transact({"from": account})

    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    print(f"Transaction mined in block {receipt['blockNumber']}")

    # Read back and verify
    print("\nReading root back from blockchain...")
    record_count = contract.functions.getRecordCount().call()
    result = contract.functions.getRoot(record_count - 1).call()

    on_chain_root = result[0].hex()
    on_chain_version = result[1]
    on_chain_creator = result[2]
    on_chain_timestamp = result[3]

    print(f"On-chain root:    {on_chain_root}")
    print(f"On-chain version: {on_chain_version}")
    print(f"On-chain creator: {on_chain_creator}")
    print(f"On-chain time:    {datetime.fromtimestamp(on_chain_timestamp, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")

    if on_chain_root == merkle_root:
        print("\nSuccess: on-chain root matches local Merkle root.")
    else:
        print("\nError: Mismatch!")
        print(f"Local root:    {merkle_root}")
        print(f"On-chain root: {on_chain_root}")
        sys.exit(1)

    print()


if __name__ == "__main__":
    main()
