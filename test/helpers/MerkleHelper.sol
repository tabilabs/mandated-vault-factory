// SPDX-License-Identifier: CC0-1.0
pragma solidity ^0.8.24;

/// @title MerkleHelper
/// @notice Minimal Merkle tree builder for fork tests. Matches OZ MerkleProof sorted-pair hashing.
library MerkleHelper {
    /// @dev Build a 2-leaf Merkle tree. Returns root and dynamic-array proofs.
    function buildTree2(bytes32 leaf0, bytes32 leaf1)
        internal
        pure
        returns (bytes32 root, bytes32[] memory proof0, bytes32[] memory proof1)
    {
        root = _hashPair(leaf0, leaf1);
        proof0 = _arr1(leaf1);
        proof1 = _arr1(leaf0);
    }

    /// @dev Build a 3-leaf Merkle tree by padding to 4 (duplicate last leaf).
    function buildTree3(bytes32 l0, bytes32 l1, bytes32 l2)
        internal
        pure
        returns (bytes32 root, bytes32[][] memory proofs)
    {
        return buildTree4(l0, l1, l2, l2);
    }

    /// @dev Build a 4-leaf Merkle tree.
    function buildTree4(bytes32 l0, bytes32 l1, bytes32 l2, bytes32 l3)
        internal
        pure
        returns (bytes32 root, bytes32[][] memory proofs)
    {
        bytes32 h01 = _hashPair(l0, l1);
        bytes32 h23 = _hashPair(l2, l3);
        root = _hashPair(h01, h23);

        proofs = new bytes32[][](4);
        proofs[0] = _arr2(l1, h23);
        proofs[1] = _arr2(l0, h23);
        proofs[2] = _arr2(l3, h01);
        proofs[3] = _arr2(l2, h01);
    }

    /// @dev Sorted-pair hash matching OpenZeppelin MerkleProof.
    function _hashPair(bytes32 a, bytes32 b) internal pure returns (bytes32) {
        return a < b ? keccak256(abi.encodePacked(a, b)) : keccak256(abi.encodePacked(b, a));
    }

    function _arr1(bytes32 a) private pure returns (bytes32[] memory out) {
        out = new bytes32[](1);
        out[0] = a;
    }

    function _arr2(bytes32 a, bytes32 b) private pure returns (bytes32[] memory out) {
        out = new bytes32[](2);
        out[0] = a;
        out[1] = b;
    }
}
