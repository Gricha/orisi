from timelock_contract.timelock_create_handler import TimelockCreateHandler
from pricecheck_contract.pricecheck_create_handler import pricecheckcreatehandler
from bounty_contract.bounty_create_handler import BountyCreateHandler
from bounty_contract.bounty_redeem_handler import GuessPasswordHandler
from transactionsigner import TransactionSigner


op_handlers = {
	'sign': TransactionSigner,
    'timelock_create': TimelockCreateHandler,
    'pricecheck_create': PricecheckCreateHandler,
    'bounty_create': BountyCreateHandler,
    'bounty_redeem': GuessPasswordHandler,
}

OPERATION_REQUIRED_FIELDS = {
    'timelock_create': ['message_id', 'sum_satoshi', 'prevtxs', 'outputs', 'miners_fee_satoshi', 'return_address', 'locktime', 'pubkey_list', 'req_sigs'],
    'pricecheck_create': ['message_id', 'sum_satoshi', 'prevtxs', 'outputs', 'miners_fee_satoshi', 'return_if_greater', 'return_if_lesser', 'price', 'locktime', 'pubkey_list', 'req_sigs'],
    'bounty_create': ['prevtx', 'locktime', 'message_id', 'sum_amount', 'miners_fee', 'oracle_fees', 'pubkey_list', 'req_sigs', 'password_hash', 'return_address'],
    'bounty_redeem': ['pwtxid', 'passwords']
}

PROTOCOL_VERSION = '0.12'

