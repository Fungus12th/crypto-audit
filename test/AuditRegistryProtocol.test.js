const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("AuditRegistry - Decentralized Protocol & Tokenomics", function () {
  let registry;
  let owner;
  let company;
  let auditor;
  let creator;

  const datasetRoot = "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
  const leaf1 = "0x1111111111111111111111111111111111111111111111111111111111111111";
  const leaf2 = "0x2222222222222222222222222222222222222222222222222222222222222222";
  const zkManifestCID = "QmZkManifestTopologyHashOnly123456789";

  beforeEach(async function () {
    [owner, company, auditor, creator] = await ethers.getSigners();
    const AuditRegistry = await ethers.getContractFactory("AuditRegistry");
    registry = await AuditRegistry.deploy();
    await registry.waitForDeployment();

    // Authorize company and auditor
    await registry.addAuditor(company.address);
    await registry.addAuditor(auditor.address);
  });

  it("should submit a staked dataset root with collateral bond and auditor fee", async function () {
    const auditorFee = ethers.parseEther("0.2");
    const totalStake = ethers.parseEther("1.2"); // 1.0 ETH bond + 0.2 ETH fee

    const tx = await registry.connect(company).submitStakedRoot(
      datasetRoot,
      "v1.0-staked",
      "Acme AI Corp",
      JSON.stringify({ model: "BioBERT" }),
      zkManifestCID,
      auditorFee,
      { value: totalStake }
    );
    await tx.wait();

    const state = await registry.getRecordProtocolState(0);
    expect(state.status).to.equal(0); // PENDING_AUDIT
    expect(state.zkManifestCID).to.equal(zkManifestCID);
    expect(state.collateralBond).to.equal(ethers.parseEther("1.0"));
    expect(state.auditorFee).to.equal(auditorFee);
  });

  it("should allow independent auditor to attest dataset and receive service fee", async function () {
    const auditorFee = ethers.parseEther("0.2");
    const totalStake = ethers.parseEther("1.2");

    await registry.connect(company).submitStakedRoot(
      datasetRoot,
      "v1.0-staked",
      "Acme AI Corp",
      "{}",
      zkManifestCID,
      auditorFee,
      { value: totalStake }
    );

    // Company CANNOT self-attest
    await expect(
      registry.connect(company).attestDataset(datasetRoot, "ipfs://audit-report-101")
    ).to.be.revertedWithCustomError(registry, "CompanyCannotSelfAttest");

    // Independent auditor attests
    const auditorBalanceBefore = await ethers.provider.getBalance(auditor.address);

    const tx = await registry.connect(auditor).attestDataset(
      datasetRoot,
      "ipfs://audit-report-101"
    );
    const receipt = await tx.wait();
    const gasUsed = receipt.gasUsed * receipt.gasPrice;

    const auditorBalanceAfter = await ethers.provider.getBalance(auditor.address);
    expect(auditorBalanceAfter + gasUsed - auditorBalanceBefore).to.equal(auditorFee);

    const state = await registry.getRecordProtocolState(0);
    expect(state.status).to.equal(1); // AUDITOR_ATTESTED
    expect(state.attestedBy).to.equal(auditor.address);
    expect(state.auditReportURI).to.equal("ipfs://audit-report-101");
    expect(state.auditorFee).to.equal(0n); // Claimed

    expect(await registry.auditorReputation(auditor.address)).to.equal(10n);
  });

  it("should register creator IP and allow proactive automated licensing", async function () {
    const simHash = "0x1234567890abcdef";
    const licenseFee = ethers.parseEther("0.05");

    // Creator registers work
    await registry.connect(creator).registerCreatorIP(
      leaf1,
      simHash,
      "Medical Research Dataset Article #101",
      licenseFee
    );

    const ip = await registry.getCreatorIP(leaf1);
    expect(ip.ipOwner).to.equal(creator.address);
    expect(ip.workTitle).to.equal("Medical Research Dataset Article #101");
    expect(ip.licenseFeeWei).to.equal(licenseFee);

    // Company registers dataset containing leaf1
    await registry.connect(company).submitStakedRoot(
      datasetRoot,
      "v1.0-clean",
      "Acme AI",
      "{}",
      zkManifestCID,
      ethers.parseEther("0.1"),
      { value: ethers.parseEther("1.1") }
    );

    // Company proactively auto-licenses the IP
    const creatorBalBefore = await ethers.provider.getBalance(creator.address);

    await registry.connect(company).autoLicenseIP(datasetRoot, leaf1, {
      value: licenseFee,
    });

    const creatorBalAfter = await ethers.provider.getBalance(creator.address);
    expect(creatorBalAfter - creatorBalBefore).to.equal(licenseFee);

    expect(await registry.isLicensedForDataset(datasetRoot, leaf1)).to.be.true;
  });

  it("should allow creator to challenge unlicensed dataset with Merkle proof and slash proportional bounty", async function () {
    const simHash = "0xaabbccddeeff0011";
    const licenseFee = ethers.parseEther("0.05");

    // 1. Creator registers IP first
    await registry.connect(creator).registerCreatorIP(
      leaf1,
      simHash,
      "Confidential Patient Genome Profile",
      licenseFee
    );

    // Helper to calculate hex ascii parent
    function hashPairHex(a, b) {
      const aClean = a.startsWith("0x") ? a.slice(2) : a;
      const bClean = b.startsWith("0x") ? b.slice(2) : b;
      const aAscii = Buffer.from(aClean, "utf-8");
      const bAscii = Buffer.from(bClean, "utf-8");
      const combined = Buffer.concat([aAscii, bAscii]);
      return ethers.sha256(combined);
    }

    // Merkle tree: leaf1 (left) + leaf2 (right) -> root
    const calculatedRoot = hashPairHex(leaf1, leaf2);

    // 2. Company submits staked dataset with 1.0 ETH collateral
    await registry.connect(company).submitStakedRoot(
      calculatedRoot,
      "v1.0-unlicensed",
      "Acme AI",
      "{}",
      zkManifestCID,
      ethers.parseEther("0.1"),
      { value: ethers.parseEther("1.1") }
    );

    // 3. Independent auditor attests dataset
    await registry.connect(auditor).attestDataset(calculatedRoot, "ipfs://report-bad");
    expect(await registry.auditorReputation(auditor.address)).to.equal(10n);

    // 4. Creator challenges with proof
    const proof = [leaf2];
    const isRightSibling = [true];

    const creatorBalBefore = await ethers.provider.getBalance(creator.address);

    const tx = await registry.connect(creator).challengeDatasetWithProof(
      calculatedRoot,
      leaf1,
      proof,
      isRightSibling
    );
    const receipt = await tx.wait();
    const gasUsed = receipt.gasUsed * receipt.gasPrice;

    const creatorBalAfter = await ethers.provider.getBalance(creator.address);
    const bounty = ethers.parseEther("0.25");
    expect(creatorBalAfter + gasUsed - creatorBalBefore).to.equal(bounty);

    // Verify dataset status is now DISPUTED_SLASHED
    const state = await registry.getRecordProtocolState(0);
    expect(state.status).to.equal(2); // DISPUTED_SLASHED
    expect(state.collateralBond).to.equal(ethers.parseEther("0.75")); // 1.0 - 0.25

    // Auditor reputation penalized
    expect(await registry.auditorReputation(auditor.address)).to.equal(0n);

    // Double claim rejected
    await expect(
      registry.connect(creator).challengeDatasetWithProof(
        calculatedRoot,
        leaf1,
        proof,
        isRightSibling
      )
    ).to.be.revertedWithCustomError(registry, "LeafAlreadyClaimed");
  });

  it("should anchor TEE hardware enclave quote hash and canary trap hash for AI model", async function () {
    await registry.connect(company).submitRoot(datasetRoot, "v1.0", "Acme AI");

    const weightsHash = "0x3333333333333333333333333333333333333333333333333333333333333333";
    const teeQuote = "0x9999999999999999999999999999999999999999999999999999999999999999";
    const canaryTrap = "0xcccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc";

    await registry.connect(company).registerModelCheckpointWithTEE(
      weightsHash,
      datasetRoot,
      "Enclave-LLM-v1",
      "PyTorch / NVIDIA H100 TEE",
      JSON.stringify({ context_length: 8192 }),
      teeQuote,
      canaryTrap
    );

    const tee = await registry.getModelCheckpointTEE(0);
    expect(tee.teeEnclaveQuoteHash).to.equal(teeQuote);
    expect(tee.canaryTrapHash).to.equal(canaryTrap);
  });
});
