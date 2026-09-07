/**
 * AuditRegistry.test.js — Unit Tests for the AuditRegistry Contract
 * ==================================================================
 * Tests:
 *   1. Should store and retrieve an audit record
 *   2. Should emit the RootSubmitted event with correct args
 *
 * Run with: npx hardhat test
 */

const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("AuditRegistry", function () {
  // Variables shared across tests
  let registry;
  let owner;

  // A sample Merkle root (32 bytes, hex-encoded)
  // In production this comes from our Python Merkle engine;
  // here we just use a hardcoded example for testing.
  const sampleRoot =
    "0xa3f2b8c1d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1";

  const datasetVersion = "v1.0";
  const creator = "test-user";

  // Deploy a fresh contract before each test
  beforeEach(async function () {
    // Get a signer (Hardhat provides 20 test accounts)
    [owner] = await ethers.getSigners();

    // Deploy the contract
    const AuditRegistry = await ethers.getContractFactory("AuditRegistry");
    registry = await AuditRegistry.deploy();
    await registry.waitForDeployment();
  });

  // ---------------------------------------------------------------
  // TEST 1: Submit and retrieve a root
  // ---------------------------------------------------------------
  it("should store and retrieve an audit record", async function () {
    // Submit a root
    const tx = await registry.submitRoot(sampleRoot, datasetVersion, creator);
    await tx.wait();

    // Retrieve it by ID (first record = ID 0)
    const result = await registry.getRoot(0);

    // result is a tuple: [root, datasetVersion, creator, timestamp]
    expect(result[0]).to.equal(sampleRoot);          // root matches
    expect(result[1]).to.equal(datasetVersion);      // version matches
    expect(result[2]).to.equal(creator);             // creator matches
    expect(result[3]).to.be.greaterThan(0);          // timestamp is set
  });

  // ---------------------------------------------------------------
  // TEST 2: Event emission
  // ---------------------------------------------------------------
  it("should emit RootSubmitted event with correct args", async function () {
    // Check that the submitRoot call emits the expected event
    await expect(registry.submitRoot(sampleRoot, datasetVersion, creator))
      .to.emit(registry, "RootSubmitted")
      .withArgs(
        0,                // id (first record)
        sampleRoot,       // root
        datasetVersion,   // version
        creator,          // creator
        // We don't check the exact timestamp — just that the event fires
        // with the right non-timestamp args. Hardhat's .withArgs checks
        // positional args, so we use a matcher for the timestamp.
        (timestamp) => timestamp > 0
      );
  });
});
