// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title AuditRegistry
 * @notice Stores Merkle roots of AI training datasets on-chain.
 *
 * This contract has exactly TWO functions:
 *   1. submitRoot()  — stores a Merkle root + metadata, emits an event
 *   2. getRoot()     — retrieves a stored record by its ID
 *
 * Raw dataset files NEVER touch the blockchain — only the 32-byte
 * Merkle root and lightweight metadata (version string, creator name,
 * and a block timestamp) are stored.
 */
contract AuditRegistry {

    // ---------------------------------------------------------------
    // DATA STRUCTURES
    // ---------------------------------------------------------------

    /**
     * @dev One audit record.
     * - root:           The 32-byte Merkle root hash
     * - datasetVersion: A human-readable version string (e.g. "v1.0")
     * - creator:        Who submitted this audit (e.g. "alice")
     * - timestamp:      Block timestamp when the record was created
     */
    struct AuditRecord {
        bytes32 root;
        string  datasetVersion;
        string  creator;
        uint256 timestamp;
    }

    // ---------------------------------------------------------------
    // STATE VARIABLES
    // ---------------------------------------------------------------

    /// @notice Array of all submitted audit records, indexed by ID.
    AuditRecord[] public records;

    // ---------------------------------------------------------------
    // EVENTS
    // ---------------------------------------------------------------

    /**
     * @notice Emitted every time a new Merkle root is submitted.
     * @param id             The index of the new record in the array
     * @param root           The Merkle root hash
     * @param datasetVersion Version string for the dataset
     * @param creator        Who submitted it
     * @param timestamp      Block timestamp
     */
    event RootSubmitted(
        uint256 indexed id,
        bytes32 root,
        string  datasetVersion,
        string  creator,
        uint256 timestamp
    );

    // ---------------------------------------------------------------
    // FUNCTIONS
    // ---------------------------------------------------------------

    /**
     * @notice Store a new Merkle root on-chain with metadata.
     * @param root           The 32-byte Merkle root of the dataset
     * @param datasetVersion A version string (e.g. "v1.0")
     * @param creator        The name or address of the submitter
     * @return id            The index of the newly created record
     *
     * How it works:
     *   1. Creates a new AuditRecord struct with the provided data
     *      plus the current block.timestamp.
     *   2. Pushes it into the records[] array.
     *   3. Emits a RootSubmitted event so off-chain listeners can
     *      react to new submissions.
     *   4. Returns the record's index (ID) so the caller knows
     *      which ID to use for getRoot() later.
     */
    function submitRoot(
        bytes32 root,
        string calldata datasetVersion,
        string calldata creator
    )
        external
        returns (uint256 id)
    {
        // The new record's ID is the current length of the array
        // (before we push), since arrays are 0-indexed.
        id = records.length;

        // Create and store the record
        records.push(AuditRecord({
            root:           root,
            datasetVersion: datasetVersion,
            creator:        creator,
            timestamp:      block.timestamp
        }));

        // Emit an event for off-chain indexing / listening
        emit RootSubmitted(id, root, datasetVersion, creator, block.timestamp);
    }

    /**
     * @notice Retrieve a previously stored audit record by its ID.
     * @param id The index of the record to retrieve
     * @return root           The Merkle root hash
     * @return datasetVersion The version string
     * @return creator        Who submitted it
     * @return timestamp      When it was submitted
     *
     * Reverts if the ID doesn't exist (Solidity's built-in
     * array bounds check handles this automatically).
     */
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
}
