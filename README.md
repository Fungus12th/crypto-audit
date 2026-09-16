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
scripts/
  deploy.js                # contract deployment script
test/
  AuditRegistry.test.js    # contract unit tests
data/                      # sample dataset files
  em-commands
  emergency
  tokens
  weak-points
.notes/
  VIVA_NOTES.md            # viva prep notes
```

## Setup

**Prerequisites:** Python 3.8+, Node.js 18+

```bash
npm install
```

```bash
pip install -r requirements.txt
```

```bash
npx hardhat compile
```

## Usage

Start the local blockchain (keep this running in its own terminal):

```bash
npx hardhat node
```

In a second terminal, deploy the contract:

```bash
npx hardhat run scripts/deploy.js --network localhost
```

Hash a dataset and get the Merkle root:

```bash
python3 python/audit.py hash-dataset ./data
```

Generate a Merkle proof for one file:

```bash
python3 python/audit.py prove ./data/example.txt --dataset ./data
```

Verify a file against a known root:

```bash
python3 python/audit.py verify ./data/example.txt --dataset ./data --root <root-hash>
```

Submit the root to the blockchain:

```bash
python3 python/submit_root.py
```

You can also specify a custom version and creator:

```bash
python3 python/submit_root.py --version v2.0 --creator your-name
```

View all stored audit records:

```bash
python3 python/read_blockchain.py
```

Works with any folder — just pass the path:

```bash
python3 python/audit.py hash-dataset ./my_photos
```

```bash
python3 python/submit_root.py ./my_photos
```

## Switching Accounts

The local Hardhat node provides 20 test accounts, each with 10,000 ETH. By default, Account #0 is used. To use a different account:

```bash
python3 python/submit_root.py --account 1
```

## Testing

```bash
npx hardhat test
```
