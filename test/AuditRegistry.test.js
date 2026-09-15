const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("AuditRegistry", function () {
  let registry;
  let owner;
  let auditor;
  let stranger;

  const sampleRoot =
    "0xa3f2b8c1d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1";
  const sampleRoot2 =
    "0x1111111111111111111111111111111111111111111111111111111111111111";
  const datasetVersion = "v1.0";
  const creator = "test-user";

  beforeEach(async function () {
    [owner, auditor, stranger] = await ethers.getSigners();
    const AuditRegistry = await ethers.getContractFactory("AuditRegistry");
    registry = await AuditRegistry.deploy();
    await registry.waitForDeployment();
  });

  // ─── Basic submit & retrieve ──────────────────────────────────────

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
        "",                                     // notes (empty via submitRoot)
        owner.address,                          // submittedBy
        (timestamp) => timestamp > 0
      );
  });

  // ─── Owner & access control ───────────────────────────────────────

  it("should set deployer as owner", async function () {
    expect(await registry.owner()).to.equal(owner.address);
  });

  it("should reject submitRoot from unauthorized address", async function () {
    await expect(
      registry.connect(stranger).submitRoot(sampleRoot, datasetVersion, creator)
    ).to.be.revertedWithCustomError(registry, "NotAuthorized");
  });

  it("should allow owner to add an auditor", async function () {
    await expect(registry.addAuditor(auditor.address))
      .to.emit(registry, "AuditorAdded")
      .withArgs(auditor.address);

    expect(await registry.authorizedAuditors(auditor.address)).to.be.true;
  });

  it("should allow an authorized auditor to submit", async function () {
    await registry.addAuditor(auditor.address);

    await expect(
      registry.connect(auditor).submitRoot(sampleRoot, datasetVersion, creator)
    ).to.emit(registry, "RootSubmitted");
  });

  it("should allow owner to remove an auditor", async function () {
    await registry.addAuditor(auditor.address);
    await registry.removeAuditor(auditor.address);

    await expect(
      registry.connect(auditor).submitRoot(sampleRoot, datasetVersion, creator)
    ).to.be.revertedWithCustomError(registry, "NotAuthorized");
  });

  it("should reject addAuditor from non-owner", async function () {
    await expect(
      registry.connect(stranger).addAuditor(stranger.address)
    ).to.be.revertedWithCustomError(registry, "NotOwner");
  });

  // ─── Pause / unpause ──────────────────────────────────────────────

  it("should allow owner to pause and block submissions", async function () {
    await expect(registry.pause())
      .to.emit(registry, "Paused")
      .withArgs(owner.address);

    await expect(
      registry.submitRoot(sampleRoot, datasetVersion, creator)
    ).to.be.revertedWithCustomError(registry, "ContractPaused");
  });

  it("should allow owner to unpause and resume submissions", async function () {
    await registry.pause();
    await expect(registry.unpause())
      .to.emit(registry, "Unpaused")
      .withArgs(owner.address);

    await expect(
      registry.submitRoot(sampleRoot, datasetVersion, creator)
    ).to.emit(registry, "RootSubmitted");
  });

  it("should reject pause from non-owner", async function () {
    await expect(
      registry.connect(stranger).pause()
    ).to.be.revertedWithCustomError(registry, "NotOwner");
  });

  // ─── Duplicate root prevention ────────────────────────────────────

  it("should reject duplicate root submission", async function () {
    await registry.submitRoot(sampleRoot, datasetVersion, creator);

    await expect(
      registry.submitRoot(sampleRoot, "v2.0", "other-user")
    ).to.be.revertedWithCustomError(registry, "DuplicateRoot");
  });

  it("should reject empty root", async function () {
    const emptyRoot = ethers.ZeroHash;
    await expect(
      registry.submitRoot(emptyRoot, datasetVersion, creator)
    ).to.be.revertedWithCustomError(registry, "EmptyRoot");
  });

  // ─── Notes ────────────────────────────────────────────────────────

  it("should store and retrieve notes via submitRootWithNotes", async function () {
    const notes = "Initial audit of training data v1";
    await registry.submitRootWithNotes(
      sampleRoot, datasetVersion, creator, notes
    );

    const result = await registry.getRecord(0);
    expect(result[0]).to.equal(sampleRoot);      // root
    expect(result[1]).to.equal(datasetVersion);   // version
    expect(result[2]).to.equal(creator);           // creator
    expect(result[3]).to.equal(notes);             // notes
    expect(result[4]).to.equal(owner.address);     // submittedBy
    expect(result[5]).to.be.greaterThan(0);        // timestamp
  });

  // ─── Record count ─────────────────────────────────────────────────

  it("should track record count", async function () {
    expect(await registry.getRecordCount()).to.equal(0);

    await registry.submitRoot(sampleRoot, datasetVersion, creator);
    expect(await registry.getRecordCount()).to.equal(1);

    await registry.submitRoot(sampleRoot2, "v2.0", creator);
    expect(await registry.getRecordCount()).to.equal(2);
  });

  // ─── getRoot backward compatibility ───────────────────────────────

  it("getRoot should still return the original 4-field tuple", async function () {
    const notes = "some notes here";
    await registry.submitRootWithNotes(
      sampleRoot, datasetVersion, creator, notes
    );

    // getRoot returns (root, version, creator, timestamp) — no notes
    const result = await registry.getRoot(0);
    expect(result.length).to.equal(4);
    expect(result[0]).to.equal(sampleRoot);
    expect(result[1]).to.equal(datasetVersion);
    expect(result[2]).to.equal(creator);
  });
});
