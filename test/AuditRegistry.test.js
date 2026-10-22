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

  // ─── On-Chain Merkle Proof Verifier ───────────────────────────────

  it("should verify a valid Merkle proof matching python/merkle.py calculation", async function () {
    const leaf0 = "0xc5a0216eb05a80c47820c3a8bceeeb6f663d3271a16cfd45bc29e5f07731abf6";
    const leaf1 = "0x008951316750d0ea2f133a24e6c28d74a0835982d07dc4948cac9c093660aea4";
    const expectedRoot = "0x7ba5bdbc1383253005928c31a1e44695f46b6c1c9030ff9465f5aae36cfbaa32";

    // 1. Before root is anchored on-chain
    let [isValid, rootAnchored] = await registry.verifyMerkleProof(
      expectedRoot,
      leaf0,
      [leaf1],
      [true]
    );
    expect(isValid).to.equal(true);
    expect(rootAnchored).to.equal(false);

    // 2. Anchor root on-chain
    await registry.submitRoot(expectedRoot, "v1.0", "Acme AI Systems");

    [isValid, rootAnchored] = await registry.verifyMerkleProof(
      expectedRoot,
      leaf0,
      [leaf1],
      [true]
    );
    expect(isValid).to.equal(true);
    expect(rootAnchored).to.equal(true);

    // 3. Verify leaf1 with left sibling (isRightSibling = false)
    const [isValid1, rootAnchored1] = await registry.verifyMerkleProof(
      expectedRoot,
      leaf1,
      [leaf0],
      [false]
    );
    expect(isValid1).to.equal(true);
    expect(rootAnchored1).to.equal(true);

    // 4. Altered leaf should fail mathematical validity
    const fakeLeaf = "0x1111111111111111111111111111111111111111111111111111111111111111";
    const [isFakeValid, fakeAnchored] = await registry.verifyMerkleProof(
      expectedRoot,
      fakeLeaf,
      [leaf1],
      [true]
    );
    expect(isFakeValid).to.equal(false);
    expect(fakeAnchored).to.equal(true);
  });

  // ─── Version Lineage & Superseding (Poisoned-Data Purge) ───────────

  it("should supersede an old root and track lineage immutably", async function () {
    const v1Root = "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
    const v2Root = "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";
    const reason = "GDPR Article 17 right-to-erasure compliance: purged patient #42";

    await registry.submitRootWithNotes(v1Root, "v1.0", "Acme Health", "v1 notes");

    // Supersede v1 with v2
    const tx = await registry.supersedeRoot(
      v1Root,
      v2Root,
      "v2.0",
      "Acme Health",
      "v2 clean dataset",
      reason
    );

    // Check event emission
    await expect(tx)
      .to.emit(registry, "RootSuperseded")
      .withArgs(v1Root, v2Root, reason, (val) => val > 0);

    // Check v1 record status
    const v1Lineage = await registry.getRecordLineage(0);
    expect(v1Lineage.parentRoot).to.equal(ethers.ZeroHash);
    expect(v1Lineage.supersededBy).to.equal(v2Root);
    expect(v1Lineage.isRevoked).to.equal(true);
    expect(v1Lineage.revocationReason).to.equal(reason);

    // Check v2 record status
    const v2Lineage = await registry.getRecordLineage(1);
    expect(v2Lineage.parentRoot).to.equal(v1Root);
    expect(v2Lineage.supersededBy).to.equal(ethers.ZeroHash);
    expect(v2Lineage.isRevoked).to.equal(false);

    // Lookup by root
    const v2ByRoot = await registry.getRecordByRoot(v2Root);
    expect(v2ByRoot.id).to.equal(1);
    expect(v2ByRoot.datasetVersion).to.equal("v2.0");
    expect(v2ByRoot.parentRoot).to.equal(v1Root);

    // Attempting to supersede an already revoked root should fail
    await expect(
      registry.supersedeRoot(
        v1Root,
        "0xcccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
        "v3.0",
        "Acme Health",
        "",
        "try again"
      )
    ).to.be.revertedWithCustomError(registry, "AlreadyRevoked");
  });

  // ─── AI Model Checkpoint Registration ─────────────────────────────

  it("should register an AI model checkpoint bound to an anchored dataset", async function () {
    const datasetRoot = "0xdddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd";
    const modelWeightsHash = "0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee";
    await registry.submitRoot(datasetRoot, "v1.0", "Acme AI Labs");

    const tx = await registry.registerModelCheckpoint(
      modelWeightsHash,
      datasetRoot,
      "MedVision-ResNet50",
      "PyTorch 2.4",
      JSON.stringify({ accuracy: 0.984, f1_score: 0.979 })
    );

    await expect(tx)
      .to.emit(registry, "ModelCheckpointRegistered")
      .withArgs(
        0,
        modelWeightsHash,
        datasetRoot,
        "MedVision-ResNet50",
        "PyTorch 2.4",
        (val) => val.includes("accuracy"),
        owner.address,
        (val) => val > 0
      );

    expect(await registry.getModelCheckpointCount()).to.equal(1);
    const checkpoint = await registry.getModelCheckpoint(0);
    expect(checkpoint.modelWeightsHash).to.equal(modelWeightsHash);
    expect(checkpoint.datasetRoot).to.equal(datasetRoot);
    expect(checkpoint.modelName).to.equal("MedVision-ResNet50");
    expect(checkpoint.framework).to.equal("PyTorch 2.4");

    // Reject duplicate checkpoint registration
    await expect(
      registry.registerModelCheckpoint(
        modelWeightsHash,
        datasetRoot,
        "Duplicate Model",
        "PyTorch",
        "{}"
      )
    ).to.be.revertedWithCustomError(registry, "ModelAlreadyRegistered");

    // Reject checkpoint bound to non-existent dataset root
    await expect(
      registry.registerModelCheckpoint(
        "0xffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
        "0x1234567890123456789012345678901234567890123456789012345678901234",
        "Orphan Model",
        "PyTorch",
        "{}"
      )
    ).to.be.revertedWithCustomError(registry, "RootNotFound");
  });
});
