import time
from sqlalchemy import text
from db import get_dest_engine, setup_logger

logger = setup_logger("refresh_mvs")

MATERIALIZED_VIEWS = [
    "public.mv_erp_lojas",
    "public.mv_erp_skus",
    "public.mv_erp_estoque_loja",
    "public.mv_erp_vendas",
    "public.mv_erp_clientes",
    "public.mv_erp_historico_compras",
    "public.mv_erp_vendedores",
    "public.mv_erp_cliente_vendedor",
    "public.mv_erp_titulos",
]

def run():
    start = time.time()
    logger.info("Iniciando refresh das materialized views...")

    dest_engine = get_dest_engine()
    failed_mvs = []

    for mv in MATERIALIZED_VIEWS:
        try:
            with dest_engine.begin() as conn:
                conn.execute(text(f"REFRESH MATERIALIZED VIEW CONCURRENTLY {mv}"))
            logger.info(f"✓ {mv} atualizada")
        except Exception as e:
            logger.exception(f"✗ Erro ao atualizar {mv}: {e}")
            failed_mvs.append(mv)

    duration = time.time() - start

    if failed_mvs:
        msg = f"Refresh concluído com {len(failed_mvs)} erro(s) em {duration:.2f}s. MVs com falha: {', '.join(failed_mvs)}"
        logger.error(msg)
        raise RuntimeError(msg)
    else:
        logger.info(f"Refresh concluído: {len(MATERIALIZED_VIEWS)} MVs atualizadas em {duration:.2f}s")
