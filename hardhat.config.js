/** @type import('hardhat/config').HardhatUserConfig */
require("@nomicfoundation/hardhat-toolbox");

module.exports = {
  solidity: "0.8.20",

  networks: {
    // Local Hardhat network — used for development and testing.
    // Start it with: npx hardhat node
    // Then deploy with: npx hardhat run scripts/deploy.js --network localhost
    localhost: {
      url: "http://127.0.0.1:8545",
    },
  },
};
