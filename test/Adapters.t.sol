// SPDX-License-Identifier: CC0-1.0
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {ERC20} from "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";

import {VenusAdapter} from "../src/adapters/VenusAdapter.sol";
import {PancakeSwapV3Adapter, IPancakeSwapV3Router} from "../src/adapters/PancakeSwapV3Adapter.sol";

contract MockERC20 is ERC20 {
    constructor(string memory name_, string memory symbol_) ERC20(name_, symbol_) {}

    function mint(address to, uint256 amount) external {
        _mint(to, amount);
    }
}

contract MockVToken is ERC20 {
    using SafeERC20 for IERC20;

    IERC20 public immutable underlyingAsset;

    constructor(IERC20 underlying_) ERC20("Mock Venus Token", "vMOCK") {
        underlyingAsset = underlying_;
    }

    function underlying() external view returns (address) {
        return address(underlyingAsset);
    }

    function mint(uint256 mintAmount) external returns (uint256) {
        underlyingAsset.safeTransferFrom(msg.sender, address(this), mintAmount);
        _mint(msg.sender, mintAmount);
        return 0;
    }

    function redeem(uint256 redeemTokens) external returns (uint256) {
        _burn(msg.sender, redeemTokens);
        underlyingAsset.safeTransfer(msg.sender, redeemTokens);
        return 0;
    }
}

contract MockPancakeRouter is IPancakeSwapV3Router {
    using SafeERC20 for IERC20;

    uint256 public constant RATE_NUMERATOR = 2;
    uint256 public constant RATE_DENOMINATOR = 1;

    function exactInputSingle(ExactInputSingleParams calldata params) external returns (uint256 amountOut) {
        require(params.deadline >= block.timestamp, "expired");
        IERC20(params.tokenIn).safeTransferFrom(msg.sender, address(this), params.amountIn);

        amountOut = (params.amountIn * RATE_NUMERATOR) / RATE_DENOMINATOR;
        require(amountOut >= params.amountOutMinimum, "slippage");

        IERC20(params.tokenOut).safeTransfer(params.recipient, amountOut);
    }
}

contract AdaptersTest is Test {
    event Supplied(
        address indexed caller,
        address indexed vToken,
        address indexed underlying,
        uint256 suppliedAmount,
        uint256 mintedAmount
    );
    event Withdrawn(
        address indexed caller,
        address indexed vToken,
        address indexed underlying,
        uint256 redeemedVTokenAmount,
        uint256 underlyingOut
    );
    event Swapped(
        address indexed caller,
        address indexed tokenIn,
        address indexed tokenOut,
        uint24 fee,
        uint256 amountIn,
        uint256 amountOut,
        uint256 amountOutMinimum,
        uint256 deadline
    );

    VenusAdapter internal venusAdapter;
    MockERC20 internal busd;
    MockERC20 internal wbnb;
    MockVToken internal vBusd;

    MockPancakeRouter internal router;
    PancakeSwapV3Adapter internal pancakeAdapter;

    address internal vault = makeAddr("vault");

    function setUp() public {
        busd = new MockERC20("BUSD", "BUSD");
        wbnb = new MockERC20("WBNB", "WBNB");
        vBusd = new MockVToken(IERC20(address(busd)));
        venusAdapter = new VenusAdapter();

        router = new MockPancakeRouter();
        pancakeAdapter = new PancakeSwapV3Adapter(address(router));
    }

    function test_venusSupplyAndWithdraw() public {
        uint256 supplyAmount = 1_000e18;
        uint256 redeemAmount = 400e18;

        busd.mint(vault, supplyAmount);

        vm.startPrank(vault);
        busd.approve(address(venusAdapter), supplyAmount);

        vm.expectEmit(true, true, true, true, address(venusAdapter));
        emit Supplied(vault, address(vBusd), address(busd), supplyAmount, supplyAmount);
        uint256 minted = venusAdapter.supply(address(vBusd), supplyAmount);
        assertEq(minted, supplyAmount, "minted vToken amount");
        assertEq(busd.balanceOf(vault), 0, "vault busd consumed");
        assertEq(vBusd.balanceOf(vault), supplyAmount, "vault received vToken");
        assertEq(busd.allowance(address(venusAdapter), address(vBusd)), 0, "adapter allowance reset");

        vBusd.approve(address(venusAdapter), redeemAmount);
        vm.expectEmit(true, true, true, true, address(venusAdapter));
        emit Withdrawn(vault, address(vBusd), address(busd), redeemAmount, redeemAmount);
        uint256 underlyingOut = venusAdapter.withdraw(address(vBusd), redeemAmount);

        vm.stopPrank();

        assertEq(underlyingOut, redeemAmount, "redeemed underlying");
        assertEq(busd.balanceOf(vault), redeemAmount, "vault recovered underlying");
        assertEq(vBusd.balanceOf(vault), supplyAmount - redeemAmount, "remaining vToken");
    }

    function test_venusSupplyRevertsWhenCallerAllowanceInsufficient() public {
        uint256 supplyAmount = 1_000e18;

        busd.mint(vault, supplyAmount);

        vm.startPrank(vault);
        busd.approve(address(venusAdapter), supplyAmount - 1);
        vm.expectRevert(
            abi.encodeWithSelector(
                VenusAdapter.InsufficientUnderlyingAllowanceFromCaller.selector, supplyAmount - 1, supplyAmount
            )
        );
        venusAdapter.supply(address(vBusd), supplyAmount);
        vm.stopPrank();
    }

    function test_venusWithdrawRevertsWhenCallerVTokenAllowanceInsufficient() public {
        uint256 supplyAmount = 1_000e18;
        uint256 redeemAmount = 400e18;

        busd.mint(vault, supplyAmount);

        vm.startPrank(vault);
        busd.approve(address(venusAdapter), supplyAmount);
        venusAdapter.supply(address(vBusd), supplyAmount);

        vBusd.approve(address(venusAdapter), redeemAmount - 1);
        vm.expectRevert(
            abi.encodeWithSelector(
                VenusAdapter.InsufficientVTokenAllowanceFromCaller.selector, redeemAmount - 1, redeemAmount
            )
        );
        venusAdapter.withdraw(address(vBusd), redeemAmount);
        vm.stopPrank();
    }

    function test_pancakeSwapSingleHop() public {
        uint256 amountIn = 500e18;
        uint256 minOut = 900e18;
        uint256 deadline = block.timestamp + 1;

        busd.mint(vault, amountIn);
        wbnb.mint(address(router), 10_000e18);

        vm.startPrank(vault);
        busd.approve(address(pancakeAdapter), amountIn);
        vm.expectEmit(true, true, true, true, address(pancakeAdapter));
        emit Swapped(vault, address(busd), address(wbnb), 2500, amountIn, 1_000e18, minOut, deadline);

        uint256 amountOut = pancakeAdapter.swap(address(busd), address(wbnb), 2500, deadline, amountIn, minOut);

        vm.stopPrank();

        assertEq(amountOut, 1_000e18, "swap output");
        assertEq(busd.balanceOf(vault), 0, "tokenIn spent");
        assertEq(wbnb.balanceOf(vault), amountOut, "vault received tokenOut");
        assertEq(busd.allowance(address(pancakeAdapter), address(router)), 0, "adapter allowance reset");
    }

    function test_pancakeSwapRevertsWhenDeadlineExpired() public {
        uint256 amountIn = 100e18;

        busd.mint(vault, amountIn);

        vm.startPrank(vault);
        busd.approve(address(pancakeAdapter), amountIn);
        vm.expectPartialRevert(PancakeSwapV3Adapter.DeadlineExpired.selector);
        pancakeAdapter.swap(address(busd), address(wbnb), 2500, block.timestamp - 1, amountIn, 1);
        vm.stopPrank();
    }

    function test_pancakeAdapterRejectsZeroRouter() public {
        vm.expectRevert(PancakeSwapV3Adapter.ZeroAddressRouter.selector);
        new PancakeSwapV3Adapter(address(0));
    }

    function test_pancakeSwapRevertsWhenIdenticalTokenPair() public {
        uint256 amountIn = 100e18;
        busd.mint(vault, amountIn);

        vm.startPrank(vault);
        busd.approve(address(pancakeAdapter), amountIn);
        vm.expectRevert(PancakeSwapV3Adapter.IdenticalTokenPair.selector);
        pancakeAdapter.swap(address(busd), address(busd), 2500, block.timestamp + 1, amountIn, 1);
        vm.stopPrank();
    }

    function test_pancakeSwapRevertsWhenZeroFee() public {
        uint256 amountIn = 100e18;
        busd.mint(vault, amountIn);

        vm.startPrank(vault);
        busd.approve(address(pancakeAdapter), amountIn);
        vm.expectRevert(PancakeSwapV3Adapter.ZeroFee.selector);
        pancakeAdapter.swap(address(busd), address(wbnb), 0, block.timestamp + 1, amountIn, 1);
        vm.stopPrank();
    }
}
