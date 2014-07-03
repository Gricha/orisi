from conditionedtransactionhandler import ConditionedTransactionHandler
from bounty_contract.bounty_create_handler import PasswordTransactionRequestHandler
from bounty_contract.bounty_redeem_handler import GuessPasswordHandler

handlers = {
    'conditioned_transaction': ConditionedTransactionHandler,
    'bounty_create': PasswordTransactionRequestHandler,
    'guess_password': GuessPasswordHandler,
}
