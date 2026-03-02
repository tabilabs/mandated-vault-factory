// SPDX-License-Identifier: CC0-1.0
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {MerkleProof} from "@openzeppelin/contracts/utils/cryptography/MerkleProof.sol";

import {MerkleHelper} from "./helpers/MerkleHelper.sol";

contract MerkleHelperTest is Test {
    function test_buildTree2_proofsVerify() public pure {
        bytes32 leaf0 = keccak256("leaf-0");
        bytes32 leaf1 = keccak256("leaf-1");

        (bytes32 root, bytes32[] memory proof0, bytes32[] memory proof1) = MerkleHelper.buildTree2(leaf0, leaf1);

        assertTrue(MerkleProof.verify(proof0, root, leaf0), "leaf0 proof should verify");
        assertTrue(MerkleProof.verify(proof1, root, leaf1), "leaf1 proof should verify");
    }

    function test_buildTree3_proofsVerifyWithPadding() public pure {
        bytes32 leaf0 = keccak256("leaf-0");
        bytes32 leaf1 = keccak256("leaf-1");
        bytes32 leaf2 = keccak256("leaf-2");

        (bytes32 root, bytes32[][] memory proofs) = MerkleHelper.buildTree3(leaf0, leaf1, leaf2);

        assertEq(proofs.length, 4, "tree3 should pad to 4 leaves");
        assertTrue(MerkleProof.verify(proofs[0], root, leaf0), "leaf0 proof should verify");
        assertTrue(MerkleProof.verify(proofs[1], root, leaf1), "leaf1 proof should verify");
        assertTrue(MerkleProof.verify(proofs[2], root, leaf2), "leaf2 proof should verify");
        assertTrue(MerkleProof.verify(proofs[3], root, leaf2), "padded leaf proof should verify");
    }

    function test_buildTree4_proofsVerify() public pure {
        bytes32 leaf0 = keccak256("leaf-0");
        bytes32 leaf1 = keccak256("leaf-1");
        bytes32 leaf2 = keccak256("leaf-2");
        bytes32 leaf3 = keccak256("leaf-3");

        (bytes32 root, bytes32[][] memory proofs) = MerkleHelper.buildTree4(leaf0, leaf1, leaf2, leaf3);

        assertEq(proofs.length, 4, "tree4 should return 4 proofs");
        assertTrue(MerkleProof.verify(proofs[0], root, leaf0), "leaf0 proof should verify");
        assertTrue(MerkleProof.verify(proofs[1], root, leaf1), "leaf1 proof should verify");
        assertTrue(MerkleProof.verify(proofs[2], root, leaf2), "leaf2 proof should verify");
        assertTrue(MerkleProof.verify(proofs[3], root, leaf3), "leaf3 proof should verify");
    }
}
