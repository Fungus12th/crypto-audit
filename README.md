# crypto-audit

Cryptographic auditing system for AI training datasets. Uses Merkle trees to fingerprint dataset files and stores the root hash on-chain via an Ethereum smart contract — so any tampering is immediately detectable.

## Tech Stack

- **Python** — SHA-256 hashing, Merkle tree construction, proof generation/verification
- **Solidity** — `AuditRegistry` smart contract for on-chain root storage
- **Hardhat** — Local Ethereum development and testing
- **web3.py** — Python-to-blockchain bridge

## Project Structure

```
contracts/
  AuditRegistry.sol        # smart contract
python/
  merkle.py                # merkle tree implementation
  audit.py                 # CLI for hashing, proving, verifying
  submit_root.py           # submits merkle root to blockchain
  read_blockchain.py       # reads stored records from chain
  tamper_demo.py           # demo: flip a byte, detect tampering
scripts/
  deploy.js                # contract deployment script
test/
  AuditRegistry.test.js    # contract unit tests
data/                      # sample dataset files
```

## Setup

**Prerequisites:** Python 3.8+, Node.js 18+

```bash
npm install
pip install -r requirements.txt
npx hardhat compile
```

## Usage

Start the local blockchain (keep this running):

```bash
npx hardhat node
```

In a second terminal:

```bash
# deploy the contract
npx hardhat run scripts/deploy.js --network localhost

# hash a dataset and get the merkle root
python3 python/audit.py hash-dataset ./data

# generate a merkle proof for one file
python3 python/audit.py prove ./data/file1.txt --dataset ./data

# verify a file against a known root
python3 python/audit.py verify ./data/file1.txt --dataset ./data --root <root-hash>

# submit the root to the blockchain
python3 python/submit_root.py

# view all stored audit records
python3 python/read_blockchain.py

# run the tamper detection demo
python3 python/tamper_demo.py
```

Works with any folder — just pass the path:

```bash
python3 python/audit.py hash-dataset ./my_photos
python3 python/submit_root.py ./my_photos
```

## Testing

```bash
npx hardhat test
```
