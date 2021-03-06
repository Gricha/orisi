from condition_evaluator.evaluator import Evaluator
from handlers.handlers import handlers
from handlers.password_transaction.password_db import RSAKeyPairs, LockedPasswordTransaction, RightGuess, SentPasswordTransaction
from handlers.password_transaction.util import Util
from oracle import Oracle
from oracle_communication import OracleCommunication
from oracle_db import OracleDb, TaskQueue, TransactionRequestDb, HandledTransaction, SignedTransaction

from settings_local import ORACLE_ADDRESS
from shared.bitmessage_communication.bitmessagemessage import BitmessageMessage
from shared.bitcoind_client.bitcoinclient import BitcoinClient

import base64
import hashlib
import json
import os
import unittest

from collections import defaultdict
from Crypto.PublicKey import RSA

TEMP_DB_FILE = 'temp_db_file.db'
TEST_ACCOUNT = 'oracle_test_account'
FAKE_TXID = '3bda4918180fd55775a24580652f4c26d898d5840c7e71313491a05ef0b743d8'
FAKE_PUBKEYS = [
  "0446ea8a207cb52c15c36bed7fb4cabc6d86df92ae0e1d32eb5274352c41fe763751150205aa93b07432030e9fe9f4a3e546925656c9ea69ab3977d5885215868d",
  "04ae31650f219e598a2c69beeb97867c9d3a292581af56ee156394f639ee4d6d7d19d2f4c9c565cc962fc5ecb5954edd1df13a8cd49962b8ebb78143c69cff7d6a",
  "04454a56bd5d554aff9001f330d87936aee45645b56139b3739dc50775c468813cfe74daca943a0d35252631f769618a4f33acb00f75a95f37d3cab55b07884309"
]
FAKE_PRIVKEYS = [
  "5JcfuBf6XcSARDjJsLuLB4JxBmVhHTHhGTqWUvsW5dPGEK6pW3i",
  "5KDdTzAiw5KZKALWk5jfxdTNwbPgVjqNf4fYdvq4pQT6enV7GrL",
  "5KQADM2LgH1JZDaSdYD6WwbukqCFFo54YDd62sE3KEnbXfscnxo"
]

def create_message(tx, prevtx, pubkeys):
  msg_dict = defaultdict(lambda: 'dummy')
  msg_dict['receivedTime'] = 1000
  msg_dict['subject'] = base64.encodestring('dummy')
  msg_dict['message'] = base64.encodestring("""
    {{
    "transactions": [{{
        "raw_transaction": "{0}",
        "prevtx": {1}
    }}],
    "pubkey_list": {2},
    "req_sigs": 4,
    "operation": "conditioned_transaction",
    "locktime": 1402318623,
    "condition": "True"}}
    """.format(tx, prevtx, pubkeys))
  message = BitmessageMessage(
      msg_dict,
      'dummyaddress')
  return message

class MockOracleDb(OracleDb):
  def __init__(self):
    self._filename = TEMP_DB_FILE
    self.connect()
    operations = {
      'conditioned_transaction': TransactionRequestDb
    }
    self.operations = defaultdict(lambda: False, operations)

class MockBitmessageCommunication:
  def broadcast_signed_transaction(self,msg_bd):
    pass

  def broadcast(self, sub, msg):
    pass

class MockOracle(Oracle):
  def __init__(self):
    self.communication = MockBitmessageCommunication()
    self.db = MockOracleDb()
    self.btc = BitcoinClient(account = TEST_ACCOUNT)
    self.evaluator = Evaluator()

    self.task_queue = TaskQueue(self.db)

    self.handlers = defaultdict(lambda: None, handlers)

class OracleTests(unittest.TestCase):
  def setUp(self):
    self.oracle = MockOracle()
    self.conditioned_request_handler = handlers['conditioned_transaction'](self.oracle)

  def tearDown(self):
    os.remove(TEMP_DB_FILE)

    # Bitcoind has limited rpc connections
    # We could change them in config, but we can just free resources
    self.oracle.btc = None
    self.oracle = None

  # Helping functions
  def get_all_addresses(self):
    return self.oracle.btc.get_addresses_for_account(TEST_ACCOUNT)

  def create_multisig(self):
    addresses = self.get_all_addresses()
    for i in range(max(0, 2 - len(addresses))):
      self.oracle.btc.get_new_address()
    addresses = self.get_all_addresses()[:2]
    pubkeys = [self.oracle.btc.validate_address(addr)['pubkey'] for addr in addresses]
    all_addresses = pubkeys + FAKE_PUBKEYS
    result = self.oracle.btc.create_multisig_address(4, all_addresses)
    multisig = result['address']
    redeem_script = result['redeemScript']
    self.oracle.btc.add_multisig_address(4, all_addresses)
    return multisig, redeem_script, all_addresses

  def create_fake_transaction(self, address, txid=FAKE_TXID, amount=1.0):
    transaction = self.oracle.btc.create_raw_transaction(
        [{"txid":txid, "vout":0}],
        {address:amount}
    )
    return transaction

  def create_unsigned_transaction(self):
    multisig, redeem_script, pubkeys = self.create_multisig()
    fake_transaction = self.create_fake_transaction(multisig)
    fake_transaction_dict = self.oracle.btc.get_json_transaction(fake_transaction)
    transaction = self.oracle.btc.create_raw_transaction(
        [{"txid":fake_transaction_dict['txid'], "vout":0}],
        {"1NJJpSgp55nQKe6DZkzg4VqxRRYcUuJSHz":1.0}
    )
    prevtxs = []
    script_pub_key = fake_transaction_dict['vout'][0]['scriptPubKey']['hex']
    prevtx = {
        "scriptPubKey": script_pub_key,
        "redeemScript": redeem_script,
        "txid": fake_transaction_dict['txid'],
        "vout": 0
    }
    prevtxs.append(prevtx)
    return (transaction, prevtxs, pubkeys)

  def create_signed_transaction(self):
    unsigned, prevtx, pubkeys = self.create_unsigned_transaction()
    signed = self.oracle.btc.sign_transaction(unsigned, prevtx, FAKE_PRIVKEYS)
    return signed, prevtx, pubkeys

  def create_conditioned_transaction_request(self):
    transaction, prevtx, pubkeys = self.create_signed_transaction()
    message = create_message(transaction, json.dumps(prevtx), json.dumps(pubkeys))
    rqhs = self.conditioned_request_handler.get_request_hash(json.loads(message.message))
    request = ('conditioned_transaction', message)
    return request, rqhs

  def add_request(self):
    request, rqhs = self.create_conditioned_transaction_request()
    self.oracle.handle_request(request)
    return rqhs

  def test_add_transaction(self):
    self.add_request()
    self.assertEqual(len(self.oracle.task_queue.get_all_tasks()), 1)

  def test_add_task(self):
    self.add_request()
    tasks = self.oracle.get_tasks()
    self.assertEqual(len(tasks), 1)

    self.oracle.task_queue.done(tasks[0])

    task = self.oracle.task_queue.get_oldest_task()
    self.assertIsNone(task)

  def test_reject_task_more_sigs(self):
    request, rqhs = self.create_conditioned_transaction_request()
    HandledTransaction(self.oracle.db).save({
        "rqhs": rqhs,
        "max_sigs": 4})

    self.oracle.handle_request(request)
    tasks = self.oracle.get_tasks()
    self.assertEqual(len(tasks), 0)

  def test_accept_task_same_sigs(self):
    request, rqhs = self.create_conditioned_transaction_request()
    HandledTransaction(self.oracle.db).save({
        "rqhs": rqhs,
        "max_sigs":3})

    self.oracle.handle_request(request)
    tasks = self.oracle.get_tasks()
    self.assertEqual(len(tasks), 1)

  def test_update_task_less_sigs(self):
    request, rqhs = self.create_conditioned_transaction_request()
    HandledTransaction(self.oracle.db).save({
        "rqhs": rqhs,
        "max_sigs":1})

    self.oracle.handle_request(request)
    tasks = self.oracle.get_tasks()
    self.assertEqual(len(tasks), 1)

    self.oracle.task_queue.done(tasks[0])

    self.assertEqual(HandledTransaction(self.oracle.db).signs_for_transaction(
        rqhs),
        3)

  def test_choosing_bigger_transaction(self):
    transaction, prevtx, pubkeys = self.create_unsigned_transaction()
    message = create_message(transaction, json.dumps(prevtx), json.dumps(pubkeys))
    request = ('conditioned_transaction', message)
    self.oracle.handle_request(request)

    rqhs = self.add_request()

    self.assertEqual(len(self.oracle.task_queue.get_all_tasks()), 2)
    tasks = self.oracle.get_tasks()
    self.assertEqual(len(tasks), 1)
    task = tasks[0]
    body = json.loads(task['json_data'])
    transaction = body['transactions'][0]
    raw_transaction = transaction['raw_transaction']
    prevtx = transaction['prevtx']

    sigs = self.oracle.btc.signatures_number(raw_transaction, prevtx)
    self.assertEqual(sigs, 3)
    self.oracle.task_queue.done(task)

    self.assertEqual(HandledTransaction(self.oracle.db).signs_for_transaction(rqhs), 3)

  def test_no_tasks(self):
    tasks = self.oracle.get_tasks()
    self.assertIsInstance(tasks, list)
    self.assertEqual(len(tasks), 0)

  def test_handle_sign(self):
    self.add_request()

    tasks = self.oracle.get_tasks()
    self.assertEqual(len(tasks), 1)
    task = tasks[0]

    self.oracle.handle_task(task)
    self.assertEqual(len(self.oracle.task_queue.get_all_tasks()), 0)

    handled_transaction = SignedTransaction(self.oracle.db).get_all()
    self.assertEqual(len(handled_transaction), 1)

    handled_transaction = handled_transaction[0]
    transaction = handled_transaction['hex_transaction']
    prevtx = json.loads(handled_transaction['prevtx'])
    signs = self.oracle.btc.signatures_number(transaction, prevtx)
    self.assertEqual(signs, 4)

  def test_signature_number(self):
    transaction, prevtx, pubkeys = self.create_signed_transaction()
    self.assertEqual(self.oracle.btc.signatures_number(transaction, prevtx), 3)

    signed_transaction = self.oracle.btc.sign_transaction(transaction, prevtx)
    self.assertEqual(self.oracle.btc.signatures_number(signed_transaction, prevtx), 4)

    unsigned_transaction, prevtx, pubkeys = self.create_unsigned_transaction()
    self.assertEqual(self.oracle.btc.signatures_number(unsigned_transaction, prevtx), 0)

    signed_transaction = self.oracle.btc.sign_transaction(unsigned_transaction, prevtx)
    self.assertEqual(self.oracle.btc.signatures_number(signed_transaction, prevtx), 2)

  # password_transaction tests
  def create_password_transaction_message(self, sum_amount, oracle_fees, prevtx, password_hash, pubkey_list):
    msg_dict = defaultdict(lambda: 'dummy')
    msg_dict['receivedTime'] = 1000
    msg_dict['subject'] = base64.encodestring('dummy')
    msg_dict['message'] = base64.encodestring("""
    {{
    "miners_fee": "0.0001",
    "return_address": "1LocAwBWdEBDxSRGDAomWFBVFCYAiKfBVx",
    "locktime": 0,
    "sum_amount": "{0}",
    "oracle_fees": {1},
    "operation": "password_transaction",
    "prevtx": {2},
    "password_hash": "{3}",
    "pubkey_list": {4},
    "req_sigs": 4
    }}
    """.format(sum_amount, oracle_fees, prevtx, password_hash, pubkey_list))
    message = BitmessageMessage(
      msg_dict,
      'dummyaddress')
    return message

  def test_rsa(self):
    handler = handlers['password_transaction'](self.oracle)
    pwtxid = hashlib.sha256('test').hexdigest()
    rsa_public_key = json.loads(handler.get_public_key(pwtxid))
    key = RSA.construct((long(rsa_public_key['n']), long(rsa_public_key['e'])))

    msg = 'test message'
    msg_encrypted = key.encrypt(msg, 0)

    rsa_key = RSAKeyPairs(self.oracle.db).get_by_pwtxid(pwtxid)
    key2 = Util.construct_key_from_data(rsa_key)

    msg_decrypted = key2.decrypt(msg_encrypted)
    self.assertEqual(msg, msg_decrypted)

  def create_password_transaction_request(self):
    multisig, redeem, pubkeys = self.create_multisig()
    txids = ["1959375b1b7fe88f5c369bf9219370a33b23ce71f0b5923dc2722ffdd99c6cca","2bf37212b70c879d24740e5466fef0e9bb8f48eea6210e69d126fc1c7109aeca"]

    fake_transactions = [self.create_fake_transaction(multisig, txids[i], 0.1) for i in range(2)]

    prevtxs = []
    for tx in fake_transactions:
      tx_dict = self.oracle.btc.get_json_transaction(tx)
      prevtx = {
        "txid": tx_dict['txid'],
        "vout": 0,
        "redeemScript":redeem,
        "scriptPubKey": tx_dict['vout'][0]['scriptPubKey']['hex']
      }
      prevtxs.append(prevtx)
    prevtxs = json.dumps(prevtxs)

    sum_amount = 0.2
    password_hash = hashlib.sha256('test').hexdigest()
    oracle_fees = json.dumps({ORACLE_ADDRESS:"0.0001"})
    pubkeys = json.dumps(pubkeys)

    message = self.create_password_transaction_message(sum_amount, oracle_fees, prevtxs, password_hash, pubkeys)
    request = ('password_transaction', message)
    return request

  def test_create_password_transaction_request(self):
    request = self.create_password_transaction_request()
    self.oracle.handle_request(request)
    locked_transactions = LockedPasswordTransaction(self.oracle.db).get_all()
    self.assertEqual(len(locked_transactions), 1)
    self.assertEqual(len(self.oracle.task_queue.get_all_tasks()), 1)

  def test_password_transaction_request_corresponds_to_protocol(self):
    oc = OracleCommunication()
    operation, message = self.create_password_transaction_request()
    self.assertEqual(oc.corresponds_to_protocol(message), 'password_transaction')

  def test_handle_expired_password_transaction(self):
    request = self.create_password_transaction_request()
    self.oracle.handle_request(request)
    tasks = self.oracle.task_queue.get_all_tasks()
    self.assertEqual(len(tasks), 1)
    task = tasks[0]

    self.oracle.handle_task(task)

  def create_guess_message(self, pwtxid, passwords):
    msg_dict = defaultdict(lambda: 'dummy')
    msg_dict['receivedTime'] = 1000
    msg_dict['subject'] = base64.encodestring('dummy')
    msg_dict['message'] = base64.encodestring("""
    {{
        "operation": "bounty_redeem",
        "pwtxid": "{0}",
        "passwords": {1}
    }}
    """.format(pwtxid, passwords))
    message = BitmessageMessage(
      msg_dict,
      'dummyaddress')
    return message

  def create_claim_password_request(self):
    request = self.create_password_transaction_request()
    self.oracle.handle_request(request)

    transactions = LockedPasswordTransaction(self.oracle.db).get_all()
    self.assertEqual(len(transactions), 1)

    transaction = transactions[0]
    pwtxid = transaction['pwtxid']
    data = json.loads(transaction['json_data'])

    guess = {
        'password': 'test',
        'address': "1AtY44R7exbYnXARs3xSEJuFdEVUMXwpUN"
    }
    rsa_pubkey = data['rsa_pubkey']
    key = Util.construct_pubkey_from_data(rsa_pubkey)

    rsa_hash = hashlib.sha256(json.dumps(rsa_pubkey)).hexdigest()

    encrypted_guess = key.encrypt(json.dumps(guess), 0)[0]
    base64_encrypted_guess = base64.encodestring(encrypted_guess)
    passwords = json.dumps({rsa_hash: base64_encrypted_guess})
    message = self.create_guess_message(pwtxid, passwords)
    request = ('bounty_redeem', message)
    return request

  def test_claim_password_transaction(self):
    request = self.create_claim_password_request()
    self.oracle.handle_request(request)

    tasks = self.oracle.task_queue.get_all_ignore_checks()
    self.assertEqual(len(tasks), 2)

    guess_tasks = [t for t in tasks if t['filter_field'].startswith('guess')]
    self.assertEqual(len(guess_tasks), 1)
    self.assertEqual(len(RightGuess(self.oracle.db).get_all()), 1)

    task = guess_tasks[0]
    self.oracle.handle_task(task)

    data = json.loads(task['json_data'])
    transaction = LockedPasswordTransaction(self.oracle.db).get_by_pwtxid(data['pwtxid'])
    self.assertEqual(transaction['done'], 1)

    sent_transactions = SentPasswordTransaction(self.oracle.db).get_all()
    self.assertEqual(len(sent_transactions), 1)
    transaction = sent_transactions[0]
    tx = transaction['tx']
    tx_dict = self.oracle.btc.get_json_transaction(tx)
    vout = tx_dict['vout']
    self.assertEqual(len(vout), 2)

    receiver_exists = False
    for o in vout:
      addr = o['scriptPubKey']['addresses'][0]
      if addr == "1AtY44R7exbYnXARs3xSEJuFdEVUMXwpUN":
        self.assertEqual(o['value'], 0.1998)
        receiver_exists = True
      else:
        self.assertEqual(o['value'], 0.0001)
    self.assertTrue(receiver_exists)

  def test_guesses_filter(self):
    request = self.create_claim_password_request()
    self.oracle.handle_request(request)

    request = self.create_claim_password_request()
    request[1].received_time_epoch = 800
    self.oracle.handle_request(request)

    tasks = self.oracle.task_queue.get_all_ignore_checks()
    self.assertEqual(len(tasks), 3)
    guess_tasks = [t for t in tasks if t['filter_field'].startswith('guess')]
    self.assertEqual(len(guess_tasks), 2)
    task = guess_tasks[0]

    final_tasks = self.oracle.handlers['bounty_redeem'](self.oracle).filter_tasks(task)
    self.assertEqual(len(final_tasks), 1)
    self.assertEqual(final_tasks[0], guess_tasks[1])
    self.oracle.handle_task(final_tasks[0])

    self.assertEqual(len(self.oracle.task_queue.get_all_ignore_checks()), 1)
