const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("AuditRegistry", function () {
  let registry;
  let owner;

  const sampleRoot =
    "0xa3f2b8c1d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1";
  const datasetVersion = "v1.0";
  const creator = "test-user";

  beforeEach(async function () {
    [owner] = await ethers.getSigners();
    const AuditRegistry = await ethers.getContractFactory("AuditRegistry");
    registry = await AuditRegistry.deploy();
    await registry.waitForDeployment();
  });

  it("should store and retrieve an audit record", async function () {
    const tx = await registry.submitRoot(sampleRoot, datasetVersion, creator);
    await tx.wait();

    const result = await registry.getRoot(0);
    expect(result[0]).to.equal(sampleRoot);
    expect(result[1]).to.equal(datasetVersion);
    expect(result[2]).to.equal(creator);
    expect(result[3]).to.be.greaterThan(0);
  });

  it("should emit RootSubmitted event with correct args", async function () {
    await expect(registry.submitRoot(sampleRoot, datasetVersion, creator))
      .to.emit(registry, "RootSubmitted")
      .withArgs(
        0,
        sampleRoot,
        datasetVersion,
        creator,
        (timestamp) => timestamp > 0
      );
  });
});
