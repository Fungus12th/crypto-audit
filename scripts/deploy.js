const fs = require("fs");
const path = require("path");

async function main() {
  const AuditRegistry = await ethers.getContractFactory("AuditRegistry");

  console.log("Deploying AuditRegistry...");
  const registry = await AuditRegistry.deploy();
  await registry.waitForDeployment();

  const address = await registry.getAddress();
  console.log(`AuditRegistry deployed to: ${address}`);

  // save address so the python scripts can pick it up
  const outputPath = path.join(__dirname, "..", "deployed_address.json");
  fs.writeFileSync(
    outputPath,
    JSON.stringify({ address: address }, null, 2)
  );
  console.log(`Address saved to deployed_address.json`);
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });
