const fs = require("fs");
const path = require("path");

async function main() {
  const [deployer, company, auditor, creator] = await ethers.getSigners();
  const AuditRegistry = await ethers.getContractFactory("AuditRegistry");

  console.log("Deploying AuditRegistry with deployer:", deployer.address);
  const registry = await AuditRegistry.deploy();
  await registry.waitForDeployment();

  const address = await registry.getAddress();
  console.log(`AuditRegistry deployed to: ${address}`);

  // Authorize Company (Account #1) and Independent Regulator/Auditor (Account #2)
  if (company) {
    const tx1 = await registry.addAuditor(company.address);
    await tx1.wait();
    console.log(`Authorized Company Submitter: ${company.address}`);
  }
  if (auditor) {
    const tx2 = await registry.addAuditor(auditor.address);
    await tx2.wait();
    console.log(`Authorized Independent Auditor: ${auditor.address}`);
  }

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
