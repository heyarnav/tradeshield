// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title TradeShieldAudit
/// @notice Immutable, tamper-evident registry of critical TradeShield audit proofs.
///
/// TradeShield's PostgreSQL database remains the system of record for all trading
/// and application data. This contract stores ONLY a minimal proof anchor for each
/// critical event:
///   - eventRef:    opaque reference ID (e.g. audit_log-audit_id or similar)
///   - eventType:   short categorical label (e.g. "TRADE_EXECUTED", "ORDER_BLOCKED")
///   - recordHash:  keccak256 of the canonical PostgreSQL audit payload
///   - anchoredAt:  block.timestamp at time of anchoring
///
/// Nothing sensitive is stored on-chain: no passwords, no JWTs, no balances, no
/// full financial records, no PII. The contract is append-only and admin-authorized
/// (the deployer / an admin address may anchor new proofs).
///
/// Verification is done off-chain: recompute the canonical PostgreSQL record hash,
/// compare it to the on-chain recordHash for that eventRef. A mismatch means the
/// local record was altered after anchoring.
///
contract TradeShieldAudit {
    /// @notice Current admin address (set to deployer; can be transferred).
    address public admin;

    /// @notice TradeShield backend contract/network identifier for the current deployment.
    ///        Stored as a UTF-8 string, e.g. "tradeshield-local:31337".
    string public immutable networkId;

    /// @notice The TradeShield backend address authorized to anchor proofs.
    ///        The Flask backend authenticates to the node separately (via local
    ///        private key / account); this is the on-chain authorization gate.
    address public backend;

    /// @notice Maximum length of eventRef / eventType strings accepted.
    uint256 public constant MAX_LABEL_LEN = 64;

    /// @notice A single anchored proof.
    struct Proof {
        bytes32 recordHash;   // keccak256 of the canonical PostgreSQL audit payload
        uint256 anchoredAt;   // block.timestamp when anchored
        bool exists;          // traceability flag (never cleared)
    }

    /// @notice All anchored proofs, keyed by eventRef.
    mapping(string => Proof) public proofs;

    /// @notice Total number of anchored proofs (useful for admin listing census).
    uint256 public totalProofs;

    /// @notice Emitted when a new proof is anchored.
    /// @param eventRef   opaque reference (e.g. "audit:<audit_id>")
    /// @param eventType  categorical label (e.g. "TRADE_EXECUTED")
    /// @param recordHash keccak256 of the canonical PostgreSQL record hash
    /// @param txHash     the blockchain tx hash that anchored this proof (set by off-chain indexer)
    /// @param anchoredAt block timestamp at anchoring time
    ///
    /// NOTE: txHash is not known inside the contract (tx.hash is only available
    /// off-chain). An indexer stores it in PostgreSQL. We emit eventRef + eventType
    /// + recordHash here so the off-chain indexer can correlate.
    event ProofAnchored(
        string eventRef,
        string eventType,
        bytes32 recordHash,
        uint256 anchoredAt
    );

    /// @notice Emitted when the authorized backend address is changed.
    event BackendUpdated(address oldBackend, address newBackend);

    /// @notice Emitted when the admin address is transferred.
    event AdminTransferred(address previousAdmin, address newAdmin);

    error TradeShieldAuthFailed();
    error TradeShieldLabelTooLong(bytes1 labelKind, string label, uint256 length, uint256 max);
    error TradeShieldEmptyLabel(bytes1 labelKind, string label);
    error TradeShieldProofExists(string eventRef);

    /// @param _networkId  identifier for this deployment (e.g. "tradeshield-local:31337")
    /// @param _backend    authorized TradeShield backend address
    /// @param _admin      initial admin address (may be same as backend or deployer)
    constructor(
        string memory _networkId,
        address _backend,
        address _admin
    ) {
        if (address(0) == _backend) revert TradeShieldAuthFailed();
        if (address(0) == _admin) revert TradeShieldAuthFailed();
        networkId = _networkId;
        backend = _backend;
        admin = _admin;
    }

    /// @notice Anchor a new audit proof on-chain.
    /// @dev  Only the authorized backend may call. eventRef must be unique.
    ///       Strings are length-limited to keep gas bounded and storage uniform.
    function anchorProof(
        string calldata _eventRef,
        string calldata _eventType,
        bytes32 _recordHash
    ) external {
        if (msg.sender != backend) revert TradeShieldAuthFailed();

        if (_eventRef.length > MAX_LABEL_LEN)
            revert TradeShieldLabelTooLong(bytes1(0x45), _eventRef, _eventRef.length, MAX_LABEL_LEN); // 'E'
        if (_eventType.length > MAX_LABEL_LEN)
            revert TradeShieldLabelTooLong(bytes1(0x54), _eventType, _eventType.length, MAX_LABEL_LEN); // 'T'
        if (_eventRef.length == 0) revert TradeShieldEmptyLabel(bytes1(0x45), _eventRef);
        if (_eventType.length == 0) revert TradeShieldEmptyLabel(bytes1(0x54), _eventType);

        if (proofs[_eventRef].exists) revert TradeShieldProofExists(_eventRef);

        proofs[_eventRef] = Proof({
            recordHash: _recordHash,
            anchoredAt: block.timestamp,
            exists: true
        });
        totalProofs += 1;

        emit ProofAnchored(_eventRef, _eventType, _recordHash, block.timestamp);
    }

    /// @notice Returns whether a proof exists for the given eventRef.
    function proofExists(string calldata _eventRef) external view returns (bool) {
        return proofs[_eventRef].exists;
    }

    /// @notice Returns the on-chain proof for an eventRef, or clears exists=false
    ///         fields when none exists (so callers can still read recordHash=0).
    function getProof(string calldata _eventRef)
        external
        view
        returns (bytes32 recordHash, uint256 anchoredAt, bool exists)
    {
        Proof storage p = proofs[_eventRef];
        return (p.recordHash, p.anchoredAt, p.exists);
    }

    /// @notice Check whether a given recordHash matches the on-chain proof for eventRef.
    /// @dev  This is the cheap on-chain component of integrity verification.
    ///       Full verification (connecting the hash to the actual PostgreSQL row) is
    ///       performed off-chain by the backend, which re-derives the canonical hash.
    function verifyProof(
        string calldata _eventRef,
        bytes32 _recordHash
    ) external view returns (bool matches, bool exists) {
        Proof storage p = proofs[_eventRef];
        return (p.exists && p.recordHash == _recordHash, p.exists);
    }

    /// @notice Update the authorized backend address.
    function setBackend(address _backend) external {
        if (msg.sender != admin) revert TradeShieldAuthFailed();
        if (address(0) == _backend) revert TradeShieldAuthFailed();
        address old = backend;
        backend = _backend;
        emit BackendUpdated(old, _backend);
    }

    /// @notice Transfer admin rights to a new address.
    function transferAdmin(address _newAdmin) external {
        if (msg.sender != admin) revert TradeShieldAuthFailed();
        if (address(0) == _newAdmin) revert TradeShieldAuthFailed();
        address prev = admin;
        admin = _newAdmin;
        emit AdminTransferred(prev, _newAdmin);
    }
}
