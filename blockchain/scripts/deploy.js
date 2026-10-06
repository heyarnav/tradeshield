import { ethers } from "hardhat";

const NETWORK_ID = "tradeshield-local:31337";

/**
 * Deploy TradeShieldAudit to the local Hardhat node.
 *
 * The authorized backend address is set to the first signer (the dev account the
 * Flask backend will use via Web3.py against the local node). In a real deployment
 * this would be the backend service account; here it is the first Hardhat default
 * account so the integration tests can anchor proofs without extra key setup.
 */
async function main() {
  const [backend, admin] = await ethers.getSigners();

  console.log("Deploying TradeShieldAudit to local Hardhat node...");
  console.log("backend address :", backend.address);
  console.log("admin address   :", admin.address);
  console.log("networkId       :", NETWORK_ID);

  const TradeShieldAudit = await ethers.getContractFactory("TradeShieldAudit");
  const contract = await TradeShieldAudit.deploy(NETWORK_ID, backend.address, admin.address);
  await contract.waitForDeployment();

  const addr = await contract.getAddress();
  console.log("TradeShieldAudit deployed to:", addr);
  console.log("network chainId         :", (await contract.provider.getNetwork()).chainId);

  return { address: addr, backend: backend.address, admin: admin.address, networkId: NETWORK_ID };
}

main().then((out) => process.exitCode = 0).catch((err) => {
  console.error(err);
  process.exit(1);
});
