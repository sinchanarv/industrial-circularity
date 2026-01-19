// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

contract SupplyChainLedger {
    
    // Define the structure of a transaction on the blockchain
    struct TransactionData {
        uint id;
        string buyer_company;
        string seller_company;
        string material;
        uint amount;
        uint timestamp;
    }

    // A mapping to store transactions by ID
    mapping(uint => TransactionData) public transactions;
    uint public transactionCount = 0;

    // Event to notify the frontend (Optional but professional)
    event TransactionRecorded(uint id, string material, uint amount);

    // Function to add a record to the blockchain
    function addTransaction(string memory _buyer, string memory _seller, string memory _material, uint _amount) public {
        transactionCount++;
        transactions[transactionCount] = TransactionData(transactionCount, _buyer, _seller, _material, _amount, block.timestamp);
        emit TransactionRecorded(transactionCount, _material, _amount);
    }

    // Function to retrieve a record
    function getTransaction(uint _id) public view returns (uint, string memory, string memory, string memory, uint, uint) {
        TransactionData memory t = transactions[_id];
        return (t.id, t.buyer_company, t.seller_company, t.material, t.amount, t.timestamp);
    }
}