import pytest

from rotkehlchen.tests.utils.exchanges import create_test_kraken


DEMO_KRAKEN_FUTURES_API_KEY = 'QjqMVj9JlFgU6OWQBJ07gTcc6k14coxcT1CsjE31AujndTdPRlHcpxCt'
DEMO_KRAKEN_FUTURES_API_SECRET = 'Wqdz0U+SNcnqa3NKUAeHyjFWa7uE5ecQzgjbftH8pw+E5KptJDN6WBweGx7V0Kvi6clJJpIwhz+0CDJ4lJGkPsXD'


@pytest.fixture(name='kraken_demo_api_key')
def fixture_kraken_demo_api_key():
    return DEMO_KRAKEN_FUTURES_API_KEY


@pytest.fixture(name='kraken_demo_api_secret')
def fixture_kraken_demo_api_secret():
    return DEMO_KRAKEN_FUTURES_API_SECRET


@pytest.fixture(name='kraken_futures_test_base_uri')
def fixture_kraken_futures_test_base_uri():
    return 'https://demo-futures.kraken.com'



@pytest.fixture(name='kraken')
def fixture_kraken(
        inquirer,  # pylint: disable=unused-argument
        function_scope_messages_aggregator,
        database,
):
    return create_test_kraken(
        database=database,
        msg_aggregator=function_scope_messages_aggregator,
    )

# @pytest.fixture(name='kraken')
# def fixture_kraken(
#         inquirer,  # pylint: disable=unused-argument
#         function_scope_messages_aggregator,
#         database,
#         kraken_demo_api_key,
#         kraken_demo_api_secret,
#         kraken_demo_base_uri,
# ):
#     return create_test_kraken(
#         name='kraken',
#         api_key=
#         database=database,
#         msg_aggregator=function_scope_messages_aggregator,
#     )
