import json
import os
import sys

from web3 import Web3
from merkle import hash_dataset, build_tree, get_root


def main():
    project_root = os.path.join(os.path.dirname(__file__), "..")

    if len(sys.argv) > 1:
        data_folder = sys.argv[1]
    else:
        data_folder = os.path.join(project_root, "data")

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

    account = w3.eth.accounts[0]
    print(f"Using account: {account}")

    # Load contract
    address_file = os.path.join(project_root, "deployed_address.json")
    if not os.path.isfile(address_file):
        print(f"Error: Cannot find {address_file}")
        print("Deploy the contract first with:")
        print("npx hardhat run scripts/deploy.js --network localhost")
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
    print(f"Loaded AuditRegistry at {contract_address}")

    # Submit root on-chain
    root_bytes32 = bytes.fromhex(merkle_root)
    dataset_version = "v1.0"
    creator = "demo-user"

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
    result = contract.functions.getRoot(0).call()

    on_chain_root = result[0].hex()
    on_chain_version = result[1]
    on_chain_creator = result[2]
    on_chain_timestamp = result[3]

    print(f"On-chain root:    {on_chain_root}")
    print(f"On-chain version: {on_chain_version}")
    print(f"On-chain creator: {on_chain_creator}")
    print(f"On-chain time:    {on_chain_timestamp}")

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
