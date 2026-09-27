import os
import time
from datetime import datetime, timedelta
from pipelines import clientes, estoque, giro
import refresh_mvs
from db import setup_logger

logger = setup_logger("scheduler")

def parse_time(time_str):
    return datetime.strptime(time_str, "%H:%M").time()

def run():
    schedule_start = parse_time(os.environ["SCHEDULE_START"])
    schedule_interval = int(os.environ["SCHEDULE_INTERVAL_MINUTES"])
    schedule_end = parse_time(os.environ["SCHEDULE_END"])

    logger.info(f"Scheduler iniciado: {schedule_start.strftime('%H:%M')} - {schedule_end.strftime('%H:%M')}, intervalo {schedule_interval} min")

    while True:
        now = datetime.now()
        today_start = datetime.combine(now.date(), schedule_start)
        today_end = datetime.combine(now.date(), schedule_end)

        if now < today_start:
            sleep_secs = (today_start - now).total_seconds()
            logger.info(f"Aguardando até {today_start.strftime('%H:%M:%S')} ({sleep_secs:.0f}s)")
            time.sleep(sleep_secs)
            continue

        if now > today_end:
            tomorrow_start = datetime.combine(now.date() + timedelta(days=1), schedule_start)
            sleep_secs = (tomorrow_start - now).total_seconds()
            logger.info(f"Fim da janela. Aguardando até amanhã {tomorrow_start.strftime('%H:%M:%S')} ({sleep_secs:.0f}s)")
            time.sleep(sleep_secs)
            continue

        logger.info("Iniciando execução da pipeline...")
        try:
            clientes.run()
            estoque.run()
            giro.run()
            refresh_mvs.run()
            logger.info("Pipeline concluída com sucesso")
        except Exception as e:
            logger.exception(f"Erro na execução: {e}")

        now = datetime.now()
        next_run = now + timedelta(minutes=schedule_interval)

        if next_run > today_end:
            tomorrow_start = datetime.combine(now.date() + timedelta(days=1), schedule_start)
            sleep_secs = (tomorrow_start - now).total_seconds()
            logger.info(f"Próxima execução será amanhã às {tomorrow_start.strftime('%H:%M:%S')} ({sleep_secs:.0f}s)")
            time.sleep(sleep_secs)
        else:
            sleep_secs = (next_run - now).total_seconds()
            logger.info(f"Próxima execução em {next_run.strftime('%H:%M:%S')} ({sleep_secs:.0f}s)")
            time.sleep(sleep_secs)

if __name__ == "__main__":
    run()
