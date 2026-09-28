# ETL Overlabel — Pipeline de sincronização Postgres

Pipeline ETL simples e direto para sincronizar dados entre dois bancos PostgreSQL: copia 3 *materialized views* de origem, insere em tabelas destino, e atualiza 9 MVs consumidoras.

## 📋 Visão Geral

- **Origem:** `dw.mv_clientes`, `dw.mv_estoque`, `dw.mv_giro_supabase` (um banco PostgreSQL)
- **Destino:** mesmas tabelas (`dw.mv_clientes`, `dw.mv_estoque`, `dw.mv_giro_supabase`) em outro banco PostgreSQL
- **Pós-carga:** refresh de 9 MVs consumidoras (`public.mv_erp_*`) no banco destino
- **Agendamento:** daemon Python (`scheduler.py`) roda entre `SCHEDULE_START` e `SCHEDULE_END`, a cada `SCHEDULE_INTERVAL_MINUTES`
- **Deploy:** Python puro (SQLAlchemy + psycopg2), gerenciado por systemd na VPS

## 🚀 Requisitos

- Python 3.8+
- PostgreSQL 12+ (origem e destino)
- Acesso TCP às duas instâncias PostgreSQL
- (Opcional) systemd na VPS, se usar daemon com auto-restart

## 📦 Instalação

### 1. Clonar/copiar projeto
```bash
cd /home/vinicius/projects/etl_overlabel
```

### 2. Criar virtual env e instalar dependências
```bash
python -m venv .venv
source .venv/bin/activate  # ou .venv\Scripts\activate no Windows
pip install -r requirements.txt
```

### 3. Configurar `.env`
```bash
cp .env.example .env
# Editar .env com credenciais reais:
# - SOURCE_DB_URL: postgresql+psycopg2://user:pass@host:5432/dbname (origem)
# - DEST_DB_URL: postgresql+psycopg2://user:pass@host:5432/dbname (destino)
# - DIAS_CARGA: (int) dias pra trás a carregar em Giro (ex: 3)
# - SCHEDULE_START: (HH:MM) primeira execução do dia (ex: 06:00)
# - SCHEDULE_INTERVAL_MINUTES: (int) intervalo entre execuções (ex: 30)
# - SCHEDULE_END: (HH:MM) última execução do dia (ex: 22:00)
```

## 🎯 Uso

### Execução única (teste/manual)
```bash
python main.py
```
Carrega: `clientes` → `estoque` → `giro` → refresh das 9 MVs. Logs em `logs/*.log`.

### Agendamento (VPS, background)
```bash
python scheduler.py
```
Loop infinito que dispara `main.py` conforme janela de horário. Logs em `logs/scheduler.log`.

## 🏗️ Estrutura de Arquivos

```
etl_overlabel/
├── README.md                    # Esta documentação
├── requirements.txt             # sqlalchemy, psycopg2-binary, python-dotenv
├── .env.example                 # Template de configuração
├── .gitignore                   # Ignora .env, logs/, venv/
│
├── db.py                        # SQLAlchemy engines, logger setup
├── main.py                      # Runner: executa 3 pipelines + refresh
├── scheduler.py                 # Daemon: agenda main.py por janela horária
├── refresh_mvs.py               # Refresh das 9 MVs consumidoras
│
├── pipelines/
│   ├── __init__.py
│   ├── clientes.py              # Full reload: dw.mv_clientes
│   ├── estoque.py               # Full reload: dw.mv_estoque
│   └── giro.py                  # Incremental: dw.mv_giro_supabase (últimos DIAS_CARGA dias)
│
├── etl-overlabel.service.example  # Systemd unit template (instalar manualmente)
└── logs/                        # Gerado em runtime (não versionado)
    ├── clientes.log
    ├── estoque.log
    ├── giro.log
    ├── refresh_mvs.log
    └── scheduler.log
```

## 🔧 Configuração Detalhada

### Variáveis de ambiente (`.env`)

| Variável | Exemplo | Descrição |
|----------|---------|-----------|
| `SOURCE_DB_URL` | `postgresql+psycopg2://user:pass@localhost:5432/erp_dw` | Conexão ao banco origem (read-only pra aplicação) |
| `DEST_DB_URL` | `postgresql+psycopg2://user:pass@dest.internal:5432/overlabel` | Conexão ao banco destino (write) |
| `DIAS_CARGA` | `3` | Dias pra trás a carregar em Giro (incremental) |
| `SCHEDULE_START` | `06:00` | Primeira execução do dia (HH:MM) |
| `SCHEDULE_INTERVAL_MINUTES` | `30` | Minutos entre execuções |
| `SCHEDULE_END` | `22:00` | Última execução do dia (HH:MM) |

### Padrão de carga

| Pipeline | Tipo | Tabela | Descrição |
|----------|------|--------|-----------|
| **clientes** | Full reload | `dw.mv_clientes` | DELETE completo + INSERT origem. ~46 colunas. |
| **estoque** | Full reload | `dw.mv_estoque` | DELETE completo + INSERT origem. ~21 colunas. |
| **giro** | Incremental | `dw.mv_giro_supabase` | DELETE (janela data) + INSERT (últimos DIAS_CARGA dias). ~43 colunas. |
| **refresh_mvs** | N/A | 9 MVs `public.mv_erp_*` | REFRESH MATERIALIZED VIEW CONCURRENTLY pra cada uma. |

**Importante:** As tabelas destino NÃO têm coluna `id`/`mv_id` — essas colunas são geradas pela view de origem via `row_number() OVER()` e descartadas antes do INSERT.

## 📊 Logs

Cada componente gera um log dedicado em `logs/`:

```
$ tail -f logs/scheduler.log
2026-09-27 06:00:01 INFO Iniciando execução da pipeline...
2026-09-27 06:01:15 INFO Pipeline concluída com sucesso
2026-09-27 06:31:15 INFO Próxima execução em 06:32:00 (45.3s)
```

```
$ tail logs/clientes.log
2026-09-27 06:00:02 INFO Iniciando pipeline clientes...
2026-09-27 06:00:10 INFO Lidas 45000 linhas na origem
2026-09-27 06:00:15 INFO Pipeline clientes concluído: 45000 linhas inseridas em 13.15s
```

## 🖥️ Deploy na VPS

### Opção 1: Systemd (recomendado, auto-restart)

#### Passo 1: Preparar projeto
```bash
sudo mkdir -p /opt/etl_overlabel
sudo chown $USER:$USER /opt/etl_overlabel
cd /opt/etl_overlabel

git clone <repo> .  # ou copiar manualmente
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Editar .env com credenciais da VPS
nano .env
```

#### Passo 2: Instalar systemd unit
```bash
sudo cp etl-overlabel.service.example /etc/systemd/system/etl-overlabel.service

# Editar se paths forem diferentes
sudo nano /etc/systemd/system/etl-overlabel.service
```

#### Passo 3: Ativar e iniciar
```bash
sudo systemctl daemon-reload
sudo systemctl enable etl-overlabel.service
sudo systemctl start etl-overlabel.service

# Verificar status
sudo systemctl status etl-overlabel.service
sudo journalctl -u etl-overlabel -f  # logs em tempo real
```

#### Parar/reiniciar
```bash
sudo systemctl stop etl-overlabel.service
sudo systemctl restart etl-overlabel.service
```

### Opção 2: Screen/tmux (para teste rápido)
```bash
screen -S etl_overlabel
source .venv/bin/activate
python scheduler.py
# Detach: Ctrl+A, D
# Reattach: screen -r etl_overlabel
```

## 🌐 Traefik e Networking

**Resposta curta:** Traefik NÃO impacta essa aplicação.

### Por que Traefik não interfere:

1. **Traefik é um reverse proxy HTTP/HTTPS** — redireciona requisições web
2. **Esta aplicação é backend Python puro** — não expõe HTTP, não é um serviço web
3. **Conexão ao banco é TCP nativa** — psycopg2 (driver Postgres nativo) abre uma conexão TCP direta na porta 5432
4. **A aplicação abstrai roteamento** — a URL do banco em `.env` resolve diretamente no nível TCP, sem passar por Traefik

### Analogia:
```
Traefik:  user → HTTP → Traefik (reverse proxy) → seu_app:8000
          ↑ rota HTTP, balanceamento de carga web

ETL:      seu_app → TCP:5432 → Postgres
          ↑ conexão direta, não passa por Traefik
```

### Se o banco estiver atrás de Traefik (cenário improvável):

Se, por algum motivo, o PostgreSQL fosse exposto via HTTP (ex.: proxy genérico), a aplicação ainda assim **não funcionaria**, porque psycopg2 espera TCP nativo, não HTTP. Não é uma limitação da arquitetura, é uma limitação do protocolo: Postgres usa protocolo binário próprio, não HTTP.

**Conclusão:** Configure `SOURCE_DB_URL` e `DEST_DB_URL` com o host e porta **TCP direto** do Postgres (ex.: `db.internal:5432`), ignore Traefik completamente.

## 🔍 Troubleshooting

### Erro: "could not connect to server"
```
Causa: host/porta/credenciais incorretas em .env
Fix: Testar conexão manualmente:
  psql "postgresql://user:pass@host:5432/dbname"
```

### Erro: "REFRESH MATERIALIZED VIEW CONCURRENTLY falhou"
```
Causa: MV destino não tem unique index
Fix: Criar índice único na MV (consultar DDL da MV)
```

### Scheduler não está rodando
```
Verificar:
  sudo systemctl status etl-overlabel.service
  sudo journalctl -u etl-overlabel -n 50  # últimas 50 linhas
  tail -f /opt/etl_overlabel/logs/scheduler.log
```

### Carga está lenta
```
Verificar volumes em logs:
  grep "linhas" logs/clientes.log logs/estoque.log logs/giro.log
Executar main.py isolado e medir (sem scheduler) para confirmar que não é latência de rede
```

## 📈 Monitoramento

### Verificar última execução bem-sucedida
```bash
grep "concluída com sucesso" logs/scheduler.log | tail -1
```

### Contar erros no dia
```bash
grep -i error logs/*.log | wc -l
```

### Ver contagem de linhas carregadas
```bash
grep "linhas inseridas" logs/clientes.log logs/estoque.log logs/giro.log
```

## 🛠️ Manutenção

### Atualizar código
```bash
cd /opt/etl_overlabel
git pull  # ou copiar manualmente
sudo systemctl restart etl-overlabel.service
```

### Rotacionar logs (opcional)
```bash
# ~/.cron.daily/etl_overlabel_logs
cd /opt/etl_overlabel
find logs/ -name "*.log" -mtime +7 -delete  # apagar logs com >7 dias
```

### Ajustar horários sem restart
```bash
nano .env  # editar SCHEDULE_* vars
sudo systemctl restart etl-overlabel.service
```

## 📝 Checklist pré-produção

- [ ] Credenciais testadas (origem + destino)
- [ ] `DIAS_CARGA` está correto pra seu caso de uso
- [ ] Horários (`SCHEDULE_START`, `SCHEDULE_END`, intervalo) fazem sentido
- [ ] Tabelas destino têm os índices únicos esperados (pra refresh CONCURRENTLY)
- [ ] Espaço em disco suficiente no `/opt/etl_overlabel` pra logs (estimar ~1-10MB/dia)
- [ ] Backup ou snapshot do banco destino antes de primeira execução
- [ ] Systemd unit instalado e testado localmente

## 📞 Suporte

Logs detalhados em `logs/`. Cada pipeline escreve seu próprio arquivo. Erros de conexão são imediatos; erros de SQL aparecem com traceback completo.

---

**Versão:** 1.0  
**Última atualização:** 2026-09-27  
**Autor:** Claude Haiku 4.5

