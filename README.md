# Cryptographic Audit for AI Models

A two-layer system that cryptographically audits AI training datasets:

1. **Python Merkle Engine** — Hashes every file in a dataset with SHA-256, builds a Merkle tree, and can generate/verify proofs for individual files.
2. **Solidity Smart Contract** — Stores Merkle roots on-chain with metadata (version, creator, timestamp) for tamper-proof audit trails.

> **Note:** This is the CLI-only version (no web UI). Everything runs in the terminal.

---

## Prerequisites

- **Python 3.8+**
- **Node.js 18+** and **npm**
- **pip** (Python package manager)

---

## Setup

### 1. Install Node dependencies (Hardhat + toolbox)

```bash
cd crypto-audit
npm install
```

### 2. Install Python dependencies (web3.py)

```bash
pip install -r requirements.txt
```

### 3. Compile the Solidity contract

```bash
npx hardhat compile
```

---

## Run Order (Full Demo)

You need **two terminal windows** for the blockchain parts.

### Terminal 1 — Start the local blockchain

```bash
cd crypto-audit
npx hardhat node
```

Leave this running. It starts a local Ethereum node at `http://127.0.0.1:8545` with 20 pre-funded test accounts.

### Terminal 2 — Everything else

#### Step 1: Deploy the smart contract

```bash
npx hardhat run scripts/deploy.js --network localhost
```

You should see:
```
✅ AuditRegistry deployed to: 0x5FbDB2315678afecb367f032d93F642f64180aa3
📄 Contract address saved to: deployed_address.json
```

#### Step 2: Hash the dataset

```bash
python3 python/audit.py hash-dataset ./data
```

This prints every file's SHA-256 hash and the final Merkle root.

#### Step 3: Generate a Merkle proof

```bash
python3 python/audit.py prove ./data/file1.txt
```

Shows the proof path (sibling hashes + directions) needed to reconstruct the root from just file1.txt.

#### Step 4: Verify a file against the root

Copy the Merkle root from Step 2 and run:

```bash
python3 python/audit.py verify ./data/file1.txt --root <paste-root-here>
```

Should print `✅ PASS`.

#### Step 5: Submit the root to the blockchain

```bash
python3 python/submit_root.py
```

This hashes the dataset, calls `submitRoot()` on the contract, reads it back with `getRoot()`, and confirms the on-chain root matches the local root.

#### Step 6: Tamper detection demo

```bash
python3 python/tamper_demo.py
```

This flips one byte in `file1.txt`, recomputes the root, shows the mismatch (`🚨 TAMPER DETECTED!`), and restores the file.

---

## Project Structure

```
crypto-audit/
├── README.md                   # This file
├── requirements.txt            # Python deps (web3)
├── package.json                # Node deps (hardhat)
├── hardhat.config.js           # Hardhat config
│
├── python/
│   ├── merkle.py               # Core Merkle tree engine
│   ├── audit.py                # CLI (hash-dataset / prove / verify)
│   ├── tamper_demo.py          # Byte-flip tamper demo
│   └── submit_root.py         # Web3.py bridge to smart contract
│
├── data/                       # Sample dataset (3 text files)
│   ├── file1.txt
│   ├── file2.txt
│   └── file3.txt
│
├── contracts/
│   └── AuditRegistry.sol      # Smart contract (2 functions only)
│
├── scripts/
│   └── deploy.js               # Hardhat deploy script
│
└── test/
    └── AuditRegistry.test.js   # Solidity unit tests
```

---

## Architecture (from the PPT)

```
Layer 1: Hashing Engine (Python)
  Raw files → SHA-256 each → Merkle Tree → Single Root Hash

Layer 2: Blockchain Anchor (Solidity)
  Root Hash + metadata → Smart Contract → Immutable on-chain record

Key point: Raw data NEVER touches the blockchain — only the 32-byte root.
```

---

## Key Concepts for Viva

- **SHA-256**: Deterministic, one-way hash. Same input → same output. Any change → wildly different hash.
- **Merkle Tree**: Binary tree of hashes. Leaves = file hashes. Each parent = hash of its two children. Root = fingerprint of ALL data.
- **Merkle Proof**: The minimal set of sibling hashes needed to recompute the root from one leaf. Allows verification without downloading the entire dataset.
- **Smart Contract**: Self-executing code on the blockchain. Our contract stores roots immutably — once submitted, they cannot be altered or deleted.
