// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;


contract AuditRegistry {
    struct AuditRecord {
        bytes32 root;
        string datasetVersion;
        string creator;
        uint256 timestamp;
    }

    AuditRecord[] public records;

    event RootSubmitted(
        uint256 indexed id,
        bytes32 root,
        string datasetVersion,
        string creator,
        uint256 timestamp
    );

    function submitRoot(
        bytes32 root,
        string calldata datasetVersion,
        string calldata creator
    ) external returns (uint256 id) {
        id = records.length;

        records.push(AuditRecord({
            root: root,
            datasetVersion: datasetVersion,
            creator: creator,
            timestamp: block.timestamp
        }));

        emit RootSubmitted(id, root, datasetVersion, creator, block.timestamp);
    }

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
