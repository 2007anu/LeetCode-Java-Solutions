from asyncio import gather
from dataclasses import dataclass
from random import choice
from typing import Any, cast

from structlog import BoundLogger

from app.commons.applications import FastAPI
from app.commons.config.app_config import AppConfig
from app.commons.context.logger import root_logger
from app.commons.database.infra import DB
from app.commons.providers.dsj_client import DSJClient
from app.commons.providers.stripe_client import StripeClientPool
from app.commons.providers.stripe_models import StripeClientSettings


@dataclass(frozen=True)
class AppContext:
    log: BoundLogger

    payout_maindb: DB
    payout_bankdb: DB
    payin_maindb: DB
    payin_paymentdb: DB
    ledger_maindb: DB
    ledger_paymentdb: DB

    stripe: StripeClientPool

    dsj_client: DSJClient

    async def close(self):
        try:
            await gather(
                # Too many Databases here, we may need to create some "manager" to push them down
                # Also current model assume each Database instance holds unique connection pool
                # The way of closing will break if we have same connection pool assigned to different Database instance
                self.payout_maindb.disconnect(),
                self.payout_bankdb.disconnect(),
                self.payin_maindb.disconnect(),
                self.payin_paymentdb.disconnect(),
                self.ledger_maindb.disconnect(),
                self.ledger_paymentdb.disconnect(),
            )
        finally:
            # shutdown the threadpool
            self.stripe.shutdown(wait=False)


async def create_app_context(config: AppConfig) -> AppContext:

    # Pick up a maindb replica upfront and use it for all instances targeting maindb
    # Not do randomization separately in each creation to reduce the chance that
    # app_context initialization fails due to any one of the replicas has outage
    selected_maindb_replica = (
        choice(config.AVAILABLE_MAINDB_REPLICAS)
        if config.AVAILABLE_MAINDB_REPLICAS
        else None
    )

    payout_maindb = DB.create_with_alternative_replica(
        db_id="payout_maindb",
        db_config=config.DEFAULT_DB_CONFIG,
        master_url=config.PAYOUT_MAINDB_MASTER_URL,
        replica_url=config.PAYOUT_MAINDB_REPLICA_URL,
        alternative_replica=selected_maindb_replica,
    )

    payin_maindb = DB.create_with_alternative_replica(
        db_id="payin_maindb",
        db_config=config.DEFAULT_DB_CONFIG,
        master_url=config.PAYIN_MAINDB_MASTER_URL,
        replica_url=config.PAYIN_MAINDB_REPLICA_URL,
        alternative_replica=selected_maindb_replica,
    )

    ledger_maindb = DB.create_with_alternative_replica(
        db_id="ledger_maindb",
        db_config=config.DEFAULT_DB_CONFIG,
        master_url=config.LEDGER_MAINDB_MASTER_URL,
        replica_url=config.LEDGER_MAINDB_REPLICA_URL,
        alternative_replica=selected_maindb_replica,
    )

    payout_bankdb = DB.create(
        db_id="payout_bankdb",
        db_config=config.DEFAULT_DB_CONFIG,
        master_url=config.PAYOUT_BANKDB_MASTER_URL,
        replica_url=config.PAYOUT_BANKDB_REPLICA_URL,
    )

    payin_paymentdb = DB.create(
        db_id="payin_paymentdb",
        db_config=config.DEFAULT_DB_CONFIG,
        master_url=config.PAYIN_PAYMENTDB_MASTER_URL,
        replica_url=config.PAYIN_PAYMENTDB_REPLICA_URL,
    )

    ledger_paymentdb = DB.create(
        db_id="ledger_paymentdb",
        db_config=config.DEFAULT_DB_CONFIG,
        master_url=config.LEDGER_PAYMENTDB_MASTER_URL,
        replica_url=config.LEDGER_PAYMENTDB_REPLICA_URL,
    )

    try:
        await payout_maindb.connect()
    except Exception:
        root_logger.exception("failed to connect to payout main db")
        raise

    try:
        await payout_bankdb.connect()
    except Exception:
        root_logger.exception("failed to connect to payout bank db")
        raise

    try:
        await payin_maindb.connect()
    except Exception:
        root_logger.exception("failed to connect to payin main db")
        raise

    try:
        await payin_paymentdb.connect()
    except Exception:
        root_logger.exception("failed to connect to payin payment db")
        raise

    try:
        await ledger_maindb.connect()
    except Exception:
        root_logger.exception("failed to connect to ledger main db")
        raise

    try:
        await ledger_paymentdb.connect()
    except Exception:
        root_logger.exception("failed to connect to ledger payment db")
        raise

    stripe = StripeClientPool(
        settings_list=[
            StripeClientSettings(
                api_key=config.STRIPE_US_SECRET_KEY.value, country="US"
            )
        ],
        max_workers=config.STRIPE_MAX_WORKERS,
    )

    dsj_client = DSJClient(
        {
            "base_url": config.DSJ_API_BASE_URL,
            "email": config.DSJ_API_USER_EMAIL.value,
            "password": config.DSJ_API_USER_PASSWORD.value,
            "jwt_token_ttl": config.DSJ_API_JWT_TOKEN_TTL,
        }
    )

    context = AppContext(
        log=root_logger,
        payout_maindb=payout_maindb,
        payout_bankdb=payout_bankdb,
        payin_maindb=payin_maindb,
        payin_paymentdb=payin_paymentdb,
        ledger_maindb=ledger_maindb,
        ledger_paymentdb=ledger_paymentdb,
        stripe=stripe,
        dsj_client=dsj_client,
    )

    context.log.debug("app context created")

    return context


def set_context_for_app(app: FastAPI, context: AppContext):
    assert "context" not in app.extra, "app context is already set"
    app.extra["context"] = cast(Any, context)


def get_context_from_app(app: FastAPI) -> AppContext:
    context = app.extra.get("context")
    assert context is not None, "app context is not set"
    assert isinstance(context, AppContext), "app context has correct type"
    return cast(AppContext, context)


def app_context_exists(app: FastAPI) -> bool:
    context = app.extra.get("context")
    return context is not None


def remove_context_for_app(app: FastAPI, context: AppContext):
    app_context = app.extra.pop("context", None)
    assert app_context is not None, "app context is not set"
    assert app_context is context
