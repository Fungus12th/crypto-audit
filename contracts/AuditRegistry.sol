// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;


contract AuditRegistry {

    // ─── State ────────────────────────────────────────────────────────

    struct AuditRecord {
        bytes32 root;
        string datasetVersion;
        string creator;
        string notes;
        address submittedBy;
        uint256 timestamp;
    }

    AuditRecord[] public records;

    address public owner;
    bool public paused;

    mapping(address => bool) public authorizedAuditors;
    mapping(bytes32 => bool) public rootExists;

    // ─── Events ───────────────────────────────────────────────────────

    event RootSubmitted(
        uint256 indexed id,
        bytes32 root,
        string datasetVersion,
        string creator,
        string notes,
        address indexed submittedBy,
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

    // ─── Constructor ──────────────────────────────────────────────────

    constructor() {
        owner = msg.sender;
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

    // ─── Core functions ───────────────────────────────────────────────

    function submitRoot(
        bytes32 root,
        string calldata datasetVersion,
        string calldata creator
    ) external onlyAuthorized whenNotPaused returns (uint256 id) {
        return _submitRoot(root, datasetVersion, creator, "");
    }

    function submitRootWithNotes(
        bytes32 root,
        string calldata datasetVersion,
        string calldata creator,
        string calldata notes
    ) external onlyAuthorized whenNotPaused returns (uint256 id) {
        return _submitRoot(root, datasetVersion, creator, notes);
    }

    function _submitRoot(
        bytes32 root,
        string calldata datasetVersion,
        string calldata creator,
        string memory notes
    ) internal returns (uint256 id) {
        if (root == bytes32(0)) revert EmptyRoot();
        if (rootExists[root]) revert DuplicateRoot(root);

        id = records.length;
        rootExists[root] = true;

        records.push(AuditRecord({
            root: root,
            datasetVersion: datasetVersion,
            creator: creator,
            notes: notes,
            submittedBy: msg.sender,
            timestamp: block.timestamp
        }));

        emit RootSubmitted(
            id, root, datasetVersion, creator, notes, msg.sender, block.timestamp
        );
    }

    // ─── View functions ───────────────────────────────────────────────

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

    function getRecordCount() external view returns (uint256) {
        return records.length;
    }
}
