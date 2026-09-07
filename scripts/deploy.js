/**
 * deploy.js — Deploy AuditRegistry to the local Hardhat network
 * ==============================================================
 * Usage:
 *   npx hardhat run scripts/deploy.js --network localhost
 *
 * This script:
 *   1. Deploys the AuditRegistry contract
 *   2. Prints the contract address
 *   3. Saves the address to deployed_address.json so the Python
 *      script (submit_root.py) can find it automatically
 */

const fs = require("fs");
const path = require("path");

async function main() {
  // Get the contract factory (Hardhat compiles it automatically)
  const AuditRegistry = await ethers.getContractFactory("AuditRegistry");

  console.log("Deploying AuditRegistry...");

  // Deploy the contract (no constructor arguments needed)
  const registry = await AuditRegistry.deploy();

  // Wait for the deployment transaction to be mined
  await registry.waitForDeployment();

  // Get the deployed contract address
  const address = await registry.getAddress();
  console.log(`✅ AuditRegistry deployed to: ${address}`);

  // Save the address to a JSON file for the Python script to read
  const outputPath = path.join(__dirname, "..", "deployed_address.json");
  fs.writeFileSync(
    outputPath,
    JSON.stringify({ address: address }, null, 2)
  );
  console.log(`📄 Contract address saved to: deployed_address.json`);
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });
