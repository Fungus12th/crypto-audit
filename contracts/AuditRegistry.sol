// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract AuditRegistry {

    // ─── Enums & Structs ──────────────────────────────────────────────

    enum AuditStatus {
        PENDING_AUDIT,
        AUDITOR_ATTESTED,
        DISPUTED_SLASHED,
        SUPERSEDED
    }

    struct AuditRecord {
        bytes32 root;
        string datasetVersion;
        string creator;
        string notes;
        address submittedBy;
        uint256 timestamp;
        bytes32 parentRoot;
        bytes32 supersededBy;
        bool isRevoked;
        string revocationReason;
        AuditStatus status;
        address attestedBy;
        string auditReportURI;
        string zkManifestCID;
        uint256 collateralBond;
        uint256 auditorFee;
    }

    struct ModelCheckpoint {
        bytes32 modelWeightsHash;
        bytes32 datasetRoot;
        string modelName;
        string framework;
        string metricsJson;
        address registeredBy;
        uint256 timestamp;
        bytes32 teeEnclaveQuoteHash;
        bytes32 canaryTrapHash;
    }

    struct CreatorIP {
        address owner;
        bytes32 exactHash;
        bytes8 perceptualSimHash;
        string workTitle;
        uint256 licenseFeeWei;
        uint256 registeredAt;
    }

    // ─── State Variables ──────────────────────────────────────────────

    AuditRecord[] public records;
    ModelCheckpoint[] public modelCheckpoints;

    address public owner;
    bool public paused;
    uint256 private _reentrancyStatus;

    mapping(address => bool) public authorizedAuditors;
    mapping(address => uint256) public auditorReputation;

    mapping(bytes32 => bool) public rootExists;
    mapping(bytes32 => uint256) public rootToRecordId;
    mapping(bytes32 => bool) public modelCheckpointExists;

    // Creator IP Registry & Proactive Licensing
    mapping(bytes32 => CreatorIP) public creatorRegistry;
    bytes32[] public registeredIPHashes;
    mapping(bytes32 => mapping(bytes32 => bool)) public isLicensedForDataset;
    mapping(bytes32 => mapping(bytes32 => bool)) public leafAlreadyClaimed;

    // ─── Events ───────────────────────────────────────────────────────

    event RootSubmitted(
        uint256 indexed id,
        bytes32 indexed root,
        string datasetVersion,
        string creator,
        string notes,
        address indexed submittedBy,
        uint256 timestamp
    );

    event StakedRootSubmitted(
        uint256 indexed id,
        bytes32 indexed root,
        string datasetVersion,
        string creator,
        string zkManifestCID,
        uint256 collateralBond,
        uint256 auditorFee,
        address indexed submittedBy,
        uint256 timestamp
    );

    event RootSuperseded(
        bytes32 indexed oldRoot,
        bytes32 indexed newRoot,
        string reason,
        uint256 timestamp
    );

    event DatasetAttested(
        bytes32 indexed root,
        address indexed auditor,
        string auditReportURI,
        uint256 feePaid,
        uint256 timestamp
    );

    event CreatorIPRegistered(
        bytes32 indexed exactHash,
        bytes8 perceptualSimHash,
        address indexed owner,
        string workTitle,
        uint256 licenseFeeWei,
        uint256 timestamp
    );

    event IPAutoLicensed(
        bytes32 indexed datasetRoot,
        bytes32 indexed creatorLeafHash,
        address indexed licensee,
        address creator,
        uint256 feePaid,
        uint256 timestamp
    );

    event DatasetChallenged(
        bytes32 indexed datasetRoot,
        bytes32 indexed creatorLeafHash,
        address indexed challenger,
        address creator,
        uint256 bountyPaid,
        uint256 remainingBond,
        uint256 timestamp
    );

    event ModelCheckpointRegistered(
        uint256 indexed id,
        bytes32 indexed modelWeightsHash,
        bytes32 indexed datasetRoot,
        string modelName,
        string framework,
        string metricsJson,
        address registeredBy,
        uint256 timestamp
    );

    event AuditorAdded(address indexed auditor);
    event AuditorRemoved(address indexed auditor);
    event Paused(address indexed by);
    event Unpaused(address indexed by);

    // ─── Errors ───────────────────────────────────────────────────────

    error NotOwner();
    error NotAuthorized();
    error ContractPaused();
    error DuplicateRoot(bytes32 root);
    error EmptyRoot();
    error RootNotFound(bytes32 root);
    error AlreadyRevoked(bytes32 root);
    error ModelAlreadyRegistered(bytes32 modelWeightsHash);
    error InsufficientPayment(uint256 provided, uint256 required);
    error CompanyCannotSelfAttest();
    error NotPendingAudit();
    error IPAlreadyRegistered(bytes32 exactHash);
    error IPNotRegistered(bytes32 exactHash);
    error AlreadyLicensed(bytes32 datasetRoot, bytes32 creatorLeafHash);
    error LeafAlreadyClaimed(bytes32 datasetRoot, bytes32 creatorLeafHash);
    error IPRegisteredAfterDataset(uint256 ipTimestamp, uint256 datasetTimestamp);
    error InvalidProof();
    error NoCollateralRemaining();
    error ReentrancyBlocked();

    // ─── Modifiers ────────────────────────────────────────────────────

    modifier onlyOwner() {
        if (msg.sender != owner) revert NotOwner();
        _;
    }

    modifier onlyAuthorized() {
        if (msg.sender != owner && !authorizedAuditors[msg.sender])
            revert NotAuthorized();
        _;
    }

    modifier whenNotPaused() {
        if (paused) revert ContractPaused();
        _;
    }

    modifier nonReentrant() {
        if (_reentrancyStatus == 2) revert ReentrancyBlocked();
        _reentrancyStatus = 2;
        _;
        _reentrancyStatus = 1;
    }

    // ─── Constructor ──────────────────────────────────────────────────

    constructor() {
        owner = msg.sender;
        _reentrancyStatus = 1;
    }

    // ─── Admin functions ──────────────────────────────────────────────

    function addAuditor(address auditor) external onlyOwner {
        authorizedAuditors[auditor] = true;
        emit AuditorAdded(auditor);
    }

    function removeAuditor(address auditor) external onlyOwner {
        authorizedAuditors[auditor] = false;
        emit AuditorRemoved(auditor);
    }

    function pause() external onlyOwner {
        paused = true;
        emit Paused(msg.sender);
    }

    function unpause() external onlyOwner {
        paused = false;
        emit Unpaused(msg.sender);
    }

    // ─── Core Submissions (Backward Compatible & Staked) ──────────────

    function submitRoot(
        bytes32 root,
        string calldata datasetVersion,
        string calldata creator
    ) external onlyAuthorized whenNotPaused returns (uint256 id) {
        return _submitRootFull(
            root,
            datasetVersion,
            creator,
            "",
            bytes32(0),
            AuditStatus.PENDING_AUDIT,
            address(0),
            "",
            "",
            0,
            0
        );
    }

    function submitRootWithNotes(
        bytes32 root,
        string calldata datasetVersion,
        string calldata creator,
        string calldata notes
    ) external onlyAuthorized whenNotPaused returns (uint256 id) {
        return _submitRootFull(
            root,
            datasetVersion,
            creator,
            notes,
            bytes32(0),
            AuditStatus.PENDING_AUDIT,
            address(0),
            "",
            "",
            0,
            0
        );
    }

    function submitStakedRoot(
        bytes32 root,
        string calldata datasetVersion,
        string calldata creator,
        string calldata notes,
        string calldata zkManifestCID,
        uint256 auditorFeeWei
    ) external payable onlyAuthorized whenNotPaused returns (uint256 id) {
        if (msg.value < auditorFeeWei)
            revert InsufficientPayment(msg.value, auditorFeeWei);
        uint256 collateral = msg.value - auditorFeeWei;

        id = _submitRootFull(
            root,
            datasetVersion,
            creator,
            notes,
            bytes32(0),
            AuditStatus.PENDING_AUDIT,
            address(0),
            "",
            zkManifestCID,
            collateral,
            auditorFeeWei
        );

        emit StakedRootSubmitted(
            id,
            root,
            datasetVersion,
            creator,
            zkManifestCID,
            collateral,
            auditorFeeWei,
            msg.sender,
            block.timestamp
        );
    }

    function supersedeRoot(
        bytes32 oldRoot,
        bytes32 newRoot,
        string calldata version,
        string calldata creator,
        string calldata notes,
        string calldata reason
    ) external onlyAuthorized whenNotPaused returns (uint256 newId) {
        if (!rootExists[oldRoot]) revert RootNotFound(oldRoot);
        uint256 oldId = rootToRecordId[oldRoot];
        AuditRecord storage oldRecord = records[oldId];
        if (oldRecord.isRevoked) revert AlreadyRevoked(oldRoot);

        oldRecord.supersededBy = newRoot;
        oldRecord.isRevoked = true;
        oldRecord.revocationReason = reason;
        oldRecord.status = AuditStatus.SUPERSEDED;

        newId = _submitRootFull(
            newRoot,
            version,
            creator,
            notes,
            oldRoot,
            AuditStatus.PENDING_AUDIT,
            address(0),
            "",
            "",
            0,
            0
        );

        emit RootSuperseded(oldRoot, newRoot, reason, block.timestamp);
    }

    function _submitRootFull(
        bytes32 root,
        string calldata datasetVersion,
        string calldata creator,
        string memory notes,
        bytes32 parentRoot,
        AuditStatus status,
        address attestedBy,
        string memory auditReportURI,
        string memory zkManifestCID,
        uint256 collateralBond,
        uint256 auditorFee
    ) internal returns (uint256 id) {
        if (root == bytes32(0)) revert EmptyRoot();
        if (rootExists[root]) revert DuplicateRoot(root);

        id = records.length;
        rootExists[root] = true;
        rootToRecordId[root] = id;

        records.push(AuditRecord({
            root: root,
            datasetVersion: datasetVersion,
            creator: creator,
            notes: notes,
            submittedBy: msg.sender,
            timestamp: block.timestamp,
            parentRoot: parentRoot,
            supersededBy: bytes32(0),
            isRevoked: false,
            revocationReason: "",
            status: status,
            attestedBy: attestedBy,
            auditReportURI: auditReportURI,
            zkManifestCID: zkManifestCID,
            collateralBond: collateralBond,
            auditorFee: auditorFee
        }));

        emit RootSubmitted(
            id, root, datasetVersion, creator, notes, msg.sender, block.timestamp
        );
    }

    // ─── Independent Regulator Attestation ────────────────────────────

    function attestDataset(
        bytes32 root,
        string calldata auditReportURI
    ) external onlyAuthorized whenNotPaused nonReentrant {
        if (!rootExists[root]) revert RootNotFound(root);
        uint256 id = rootToRecordId[root];
        AuditRecord storage record = records[id];

        if (msg.sender == record.submittedBy) revert CompanyCannotSelfAttest();
        if (record.status != AuditStatus.PENDING_AUDIT) revert NotPendingAudit();

        record.status = AuditStatus.AUDITOR_ATTESTED;
        record.attestedBy = msg.sender;
        record.auditReportURI = auditReportURI;

        uint256 fee = record.auditorFee;
        record.auditorFee = 0;

        auditorReputation[msg.sender] += 10;

        if (fee > 0) {
            (bool success, ) = payable(msg.sender).call{value: fee}("");
            require(success, "Auditor fee transfer failed");
        }

        emit DatasetAttested(root, msg.sender, auditReportURI, fee, block.timestamp);
    }

    // ─── Permissionless Creator IP Registry & Proactive Licensing ─────

    function registerCreatorIP(
        bytes32 exactHash,
        bytes8 perceptualSimHash,
        string calldata workTitle,
        uint256 licenseFeeWei
    ) external whenNotPaused {
        if (exactHash == bytes32(0)) revert EmptyRoot();
        if (creatorRegistry[exactHash].owner != address(0))
            revert IPAlreadyRegistered(exactHash);

        creatorRegistry[exactHash] = CreatorIP({
            owner: msg.sender,
            exactHash: exactHash,
            perceptualSimHash: perceptualSimHash,
            workTitle: workTitle,
            licenseFeeWei: licenseFeeWei,
            registeredAt: block.timestamp
        });
        registeredIPHashes.push(exactHash);

        emit CreatorIPRegistered(
            exactHash,
            perceptualSimHash,
            msg.sender,
            workTitle,
            licenseFeeWei,
            block.timestamp
        );
    }

    function autoLicenseIP(
        bytes32 datasetRoot,
        bytes32 creatorLeafHash
    ) external payable whenNotPaused nonReentrant {
        if (!rootExists[datasetRoot]) revert RootNotFound(datasetRoot);
        CreatorIP storage ip = creatorRegistry[creatorLeafHash];
        if (ip.owner == address(0)) revert IPNotRegistered(creatorLeafHash);
        if (isLicensedForDataset[datasetRoot][creatorLeafHash])
            revert AlreadyLicensed(datasetRoot, creatorLeafHash);
        if (msg.value < ip.licenseFeeWei)
            revert InsufficientPayment(msg.value, ip.licenseFeeWei);

        isLicensedForDataset[datasetRoot][creatorLeafHash] = true;

        (bool success, ) = payable(ip.owner).call{value: msg.value}("");
        require(success, "License fee transfer failed");

        emit IPAutoLicensed(
            datasetRoot,
            creatorLeafHash,
            msg.sender,
            ip.owner,
            msg.value,
            block.timestamp
        );
    }

    // ─── Multi-Victim Proportional Slashing with EVM Proof Verification ─

    function challengeDatasetWithProof(
        bytes32 datasetRoot,
        bytes32 creatorLeafHash,
        bytes32[] calldata proof,
        bool[] calldata isRightSibling
    ) external whenNotPaused nonReentrant {
        if (!rootExists[datasetRoot]) revert RootNotFound(datasetRoot);
        uint256 recordId = rootToRecordId[datasetRoot];
        AuditRecord storage record = records[recordId];

        CreatorIP storage ip = creatorRegistry[creatorLeafHash];
        if (ip.owner == address(0)) revert IPNotRegistered(creatorLeafHash);
        if (ip.registeredAt > record.timestamp)
            revert IPRegisteredAfterDataset(ip.registeredAt, record.timestamp);
        if (isLicensedForDataset[datasetRoot][creatorLeafHash])
            revert AlreadyLicensed(datasetRoot, creatorLeafHash);
        if (leafAlreadyClaimed[datasetRoot][creatorLeafHash])
            revert LeafAlreadyClaimed(datasetRoot, creatorLeafHash);

        (bool isValid, ) = verifyMerkleProof(datasetRoot, creatorLeafHash, proof, isRightSibling);
        if (!isValid) revert InvalidProof();

        uint256 bounty = 0.25 ether;
        if (record.collateralBond < bounty) {
            bounty = record.collateralBond;
        }
        if (bounty == 0) revert NoCollateralRemaining();

        record.collateralBond -= bounty;
        leafAlreadyClaimed[datasetRoot][creatorLeafHash] = true;
        record.status = AuditStatus.DISPUTED_SLASHED;

        // Penalize auditor reputation if dataset was attested
        if (record.attestedBy != address(0)) {
            if (auditorReputation[record.attestedBy] >= 15) {
                auditorReputation[record.attestedBy] -= 15;
            } else {
                auditorReputation[record.attestedBy] = 0;
            }
        }

        (bool success, ) = payable(ip.owner).call{value: bounty}("");
        require(success, "Bounty transfer failed");

        emit DatasetChallenged(
            datasetRoot,
            creatorLeafHash,
            msg.sender,
            ip.owner,
            bounty,
            record.collateralBond,
            block.timestamp
        );
    }

    // ─── AI Model Provenance & TEE Hardware Enclave Attestation ───────

    function registerModelCheckpoint(
        bytes32 modelWeightsHash,
        bytes32 datasetRoot,
        string calldata modelName,
        string calldata framework,
        string calldata metricsJson
    ) external onlyAuthorized whenNotPaused returns (uint256 id) {
        return registerModelCheckpointWithTEE(
            modelWeightsHash,
            datasetRoot,
            modelName,
            framework,
            metricsJson,
            bytes32(0),
            bytes32(0)
        );
    }

    function registerModelCheckpointWithTEE(
        bytes32 modelWeightsHash,
        bytes32 datasetRoot,
        string calldata modelName,
        string calldata framework,
        string calldata metricsJson,
        bytes32 teeEnclaveQuoteHash,
        bytes32 canaryTrapHash
    ) public onlyAuthorized whenNotPaused returns (uint256 id) {
        if (modelWeightsHash == bytes32(0)) revert EmptyRoot();
        if (!rootExists[datasetRoot]) revert RootNotFound(datasetRoot);
        if (modelCheckpointExists[modelWeightsHash])
            revert ModelAlreadyRegistered(modelWeightsHash);

        id = modelCheckpoints.length;
        modelCheckpointExists[modelWeightsHash] = true;

        modelCheckpoints.push(ModelCheckpoint({
            modelWeightsHash: modelWeightsHash,
            datasetRoot: datasetRoot,
            modelName: modelName,
            framework: framework,
            metricsJson: metricsJson,
            registeredBy: msg.sender,
            timestamp: block.timestamp,
            teeEnclaveQuoteHash: teeEnclaveQuoteHash,
            canaryTrapHash: canaryTrapHash
        }));

        emit ModelCheckpointRegistered(
            id,
            modelWeightsHash,
            datasetRoot,
            modelName,
            framework,
            metricsJson,
            msg.sender,
            block.timestamp
        );
    }

    // ─── On-Chain Merkle Proof Verifier ──────────────────────────────

    function _toHexAscii(bytes32 data) internal pure returns (bytes memory) {
        bytes memory s = new bytes(64);
        bytes memory hexChars = "0123456789abcdef";
        for (uint256 i = 0; i < 32; i++) {
            uint8 b = uint8(data[i]);
            s[2 * i] = hexChars[b >> 4];
            s[2 * i + 1] = hexChars[b & 0x0f];
        }
        return s;
    }

    function verifyMerkleProof(
        bytes32 root,
        bytes32 leaf,
        bytes32[] memory proof,
        bool[] memory isRightSibling
    ) public view returns (bool isValid, bool rootAnchored) {
        if (proof.length != isRightSibling.length) return (false, false);
        bytes32 current = leaf;
        for (uint256 i = 0; i < proof.length; i++) {
            bytes32 sibling = proof[i];
            bytes memory leftAscii;
            bytes memory rightAscii;
            if (isRightSibling[i]) {
                leftAscii = _toHexAscii(current);
                rightAscii = _toHexAscii(sibling);
            } else {
                leftAscii = _toHexAscii(sibling);
                rightAscii = _toHexAscii(current);
            }
            current = sha256(abi.encodePacked(leftAscii, rightAscii));
        }
        isValid = (current == root);
        rootAnchored = rootExists[root];
    }

    // ─── View Functions (100% Backward Compatible) ────────────────────

    function getRoot(uint256 id)
        external
        view
        returns (
            bytes32 root,
            string memory datasetVersion,
            string memory creator,
            uint256 timestamp
        )
    {
        AuditRecord storage record = records[id];
        return (
            record.root,
            record.datasetVersion,
            record.creator,
            record.timestamp
        );
    }

    function getRecord(uint256 id)
        external
        view
        returns (
            bytes32 root,
            string memory datasetVersion,
            string memory creator,
            string memory notes,
            address submittedBy,
            uint256 timestamp
        )
    {
        AuditRecord storage record = records[id];
        return (
            record.root,
            record.datasetVersion,
            record.creator,
            record.notes,
            record.submittedBy,
            record.timestamp
        );
    }

    function getRecordLineage(uint256 id)
        external
        view
        returns (
            bytes32 parentRoot,
            bytes32 supersededBy,
            bool isRevoked,
            string memory revocationReason
        )
    {
        AuditRecord storage record = records[id];
        return (
            record.parentRoot,
            record.supersededBy,
            record.isRevoked,
            record.revocationReason
        );
    }

    function getRecordByRoot(bytes32 root)
        external
        view
        returns (
            uint256 id,
            string memory datasetVersion,
            string memory creator,
            string memory notes,
            address submittedBy,
            uint256 timestamp,
            bytes32 parentRoot,
            bytes32 supersededBy,
            bool isRevoked,
            string memory revocationReason
        )
    {
        if (!rootExists[root]) revert RootNotFound(root);
        id = rootToRecordId[root];
        AuditRecord storage record = records[id];
        return (
            id,
            record.datasetVersion,
            record.creator,
            record.notes,
            record.submittedBy,
            record.timestamp,
            record.parentRoot,
            record.supersededBy,
            record.isRevoked,
            record.revocationReason
        );
    }

    function getRecordProtocolState(uint256 id)
        external
        view
        returns (
            AuditStatus status,
            address attestedBy,
            string memory auditReportURI,
            string memory zkManifestCID,
            uint256 collateralBond,
            uint256 auditorFee
        )
    {
        AuditRecord storage r = records[id];
        return (
            r.status,
            r.attestedBy,
            r.auditReportURI,
            r.zkManifestCID,
            r.collateralBond,
            r.auditorFee
        );
    }

    function getRecordProtocolStateByRoot(bytes32 root)
        external
        view
        returns (
            AuditStatus status,
            address attestedBy,
            string memory auditReportURI,
            string memory zkManifestCID,
            uint256 collateralBond,
            uint256 auditorFee
        )
    {
        if (!rootExists[root]) revert RootNotFound(root);
        uint256 id = rootToRecordId[root];
        AuditRecord storage r = records[id];
        return (
            r.status,
            r.attestedBy,
            r.auditReportURI,
            r.zkManifestCID,
            r.collateralBond,
            r.auditorFee
        );
    }

    function getRecordCount() external view returns (uint256) {
        return records.length;
    }

    function getModelCheckpointCount() external view returns (uint256) {
        return modelCheckpoints.length;
    }

    function getModelCheckpoint(uint256 id)
        external
        view
        returns (
            bytes32 modelWeightsHash,
            bytes32 datasetRoot,
            string memory modelName,
            string memory framework,
            string memory metricsJson,
            address registeredBy,
            uint256 timestamp
        )
    {
        ModelCheckpoint storage m = modelCheckpoints[id];
        return (
            m.modelWeightsHash,
            m.datasetRoot,
            m.modelName,
            m.framework,
            m.metricsJson,
            m.registeredBy,
            m.timestamp
        );
    }

    function getModelCheckpointTEE(uint256 id)
        external
        view
        returns (
            bytes32 teeEnclaveQuoteHash,
            bytes32 canaryTrapHash
        )
    {
        ModelCheckpoint storage m = modelCheckpoints[id];
        return (
            m.teeEnclaveQuoteHash,
            m.canaryTrapHash
        );
    }

    function getCreatorIP(bytes32 exactHash)
        external
        view
        returns (
            address ipOwner,
            bytes32 hash,
            bytes8 perceptualSimHash,
            string memory workTitle,
            uint256 licenseFeeWei,
            uint256 registeredAt
        )
    {
        CreatorIP storage ip = creatorRegistry[exactHash];
        return (
            ip.owner,
            ip.exactHash,
            ip.perceptualSimHash,
            ip.workTitle,
            ip.licenseFeeWei,
            ip.registeredAt
        );
    }

    function getCreatorIPCount() external view returns (uint256) {
        return registeredIPHashes.length;
    }

    function getCreatorIPByIndex(uint256 index)
        external
        view
        returns (
            address ipOwner,
            bytes32 hash,
            bytes8 perceptualSimHash,
            string memory workTitle,
            uint256 licenseFeeWei,
            uint256 registeredAt
        )
    {
        bytes32 h = registeredIPHashes[index];
        return this.getCreatorIP(h);
    }
}
