# Documentação da Arquitetura — ETL Overlabel

Este documento explica **por que** essa aplicação existe, **como funciona**, e **quais são seus componentes**, sem assumir conhecimento prévio de ETL ou arquitetura de software.

---

## 🎯 O Problema

Imagine que você tem **dois bancos de dados PostgreSQL** em lugares diferentes:

- **Banco A (origem):** Sistema ERP que gera dados de clientes, estoque e vendas
- **Banco B (destino):** Sistema de análise/dashboard que precisa desses dados atualizados

**Desafio:** Como copiar dados de A pra B, **automaticamente**, **periodicamente**, sem intervir manualmente?

**Solução:** Esta aplicação.

---

## 🏗️ Arquitetura em Alto Nível

```
┌─────────────────────────────────────────────────────────┐
│                         VPS (servidor)                   │
│  ┌──────────────────────────────────────────────────┐   │
│  │  Python scheduler.py (roda sempre em background)│   │
│  │  ├─ 06:00 → dispara main.py                      │   │
│  │  ├─ 06:30 → dispara main.py                      │   │
│  │  ├─ 07:00 → dispara main.py                      │   │
│  │  └─ ... (a cada 30 min até 22:00)               │   │
│  └──────────────────────────────────────────────────┘   │
│           ↓ (cada vez que dispara)                      │
│  ┌──────────────────────────────────────────────────┐   │
│  │  main.py (orquestra a carga de dados)           │   │
│  │  1. clientes.py  → copia clientes               │   │
│  │  2. estoque.py   → copia estoque                │   │
│  │  3. giro.py      → copia vendas (últimos 3 dias)│   │
│  │  4. refresh_mvs.py → atualiza 9 views           │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
     ↓ (conecta via TCP)                ↓ (conecta via TCP)
┌──────────────────┐                ┌──────────────────┐
│ Banco PostgreSQL │                │ Banco PostgreSQL │
│    (Origem)      │                │   (Destino)      │
│                  │                │                  │
│ dw.mv_clientes   │                │ dw.mv_clientes   │
│ dw.mv_estoque    │  cópia dados   │ dw.mv_estoque    │
│ dw.mv_giro...    │ ────────────→  │ dw.mv_giro...    │
│                  │                │                  │
│ (90 mil linhas)  │                │ (90 mil linhas)  │
└──────────────────┘                └──────────────────┘
```

**Fluxo resumido:**
1. Scheduler acorda a cada 30 min
2. Main.py lê dados do banco origem
3. Main.py escreve no banco destino
4. Refresh_mvs atualiza "views" que outras apps consultam
5. Scheduler volta a dormir, volta a acordar em 30 min

---

## 📚 Componentes Principais

### 1. **scheduler.py** — O Despertador

**O que faz:** Fica rodando 24/7 em background, despertando em horários específicos.

**Analogia:** Como um alarme de relógio que toca a cada 30 minutos durante o dia (6h até 22h).

**Configuração (.env):**
```
SCHEDULE_START=06:00        ← primeira execução do dia
SCHEDULE_INTERVAL_MINUTES=30 ← intervalo entre execuções
SCHEDULE_END=22:00          ← última execução do dia
```

**Lógica:**
```python
while True:  # roda sempre
    agora = hora_atual()
    if agora < 06:00:
        espera até 06:00
    elif agora > 22:00:
        espera até amanhã 06:00
    else:
        executa main.py
        aguarda próximo intervalo (30 min)
```

**Vantagens:**
- Não precisa configurar cron do servidor
- Auto-ajusta se o servidor reinicia
- Logs próprios pra debugar se algo dá errado

---

### 2. **main.py** — O Orquestrador

**O que faz:** Coordena a execução dos 4 pipelines na ordem correta.

**Pseudocódigo:**
```
clientes.run()      # Carrega clientes
estoque.run()       # Carrega estoque
giro.run()          # Carrega giro de vendas
refresh_mvs.run()   # Atualiza as "views" consumidoras
```

**Por que essa ordem?**
- Clientes e estoque são "base de dados"
- Giro depende deles existirem
- Depois de tudo carregado, atualizar as views que outras apps consultam

---

### 3. **Pipelines** (clientes.py, estoque.py, giro.py)

Cada pipeline faz a mesma coisa em 4 etapas:

```
┌────────────────────────────────┐
│  1. Conectar ao banco origem   │
│     (ler dados de uma "view")  │
└────────────────┬───────────────┘
                 ↓
┌────────────────────────────────┐
│  2. Limpar banco destino       │
│     (DELETE de tudo)           │
└────────────────┬───────────────┘
                 ↓
┌────────────────────────────────┐
│  3. Inserir dados novos        │
│     (INSERT em lote)           │
└────────────────┬───────────────┘
                 ↓
┌────────────────────────────────┐
│  4. Registrar sucesso em log   │
│     (quantas linhas, quanto    │
│      tempo levou)              │
└────────────────────────────────┘
```

**Tipos de carga:**

| Pipeline | Tipo | O que faz |
|----------|------|----------|
| **clientes** | Full reload | Apaga TUDO, carrega tudo de novo (45k linhas) |
| **estoque** | Full reload | Apaga TUDO, carrega tudo de novo (100k linhas) |
| **giro** | Incremental | Apaga últimos 3 dias, carrega últimos 3 dias (50k linhas) |

**Por que Giro é incremental?**
- Clientes e estoque mudam pouco, refazer é barato
- Giro é dados de venda **históricos** — se carregasse tudo desde o início do tempo, seria lentíssimo
- Solução: carregar só os últimos 3 dias, substituindo dados possivelmente ajustados

---

### 4. **refresh_mvs.py** — Atualiza as "Views"

**O que é uma View?** É uma "consulta salva" no banco — outras aplicações consultam ela em vez de consultarem as tabelas originais.

**Analogia:** Se as tabelas de dados são a "cozinha", as views são o "buffet pronto" que os clientes consultam.

```
┌─ Tabela: dw.mv_clientes (90k linhas, acaba de atualizar)
└─ View: public.mv_erp_clientes (consulta que soma outras coisas)
    └─ Aplicação de dashboard consulta: SELECT * FROM public.mv_erp_clientes

Problema: A view tem dados "velhos" até alguém disser "recalcule"
Solução: REFRESH MATERIALIZED VIEW CONCURRENTLY public.mv_erp_clientes
```

**Nossas 9 views atualizadas:**
```
public.mv_erp_lojas
public.mv_erp_skus
public.mv_erp_estoque_loja
public.mv_erp_vendas
public.mv_erp_clientes
public.mv_erp_historico_compras
public.mv_erp_vendedores
public.mv_erp_cliente_vendedor
public.mv_erp_titulos
```

**Característica importante:** Se uma view falhar (ex: índice único não existe), a aplicação **continua atualizando as outras 8**, só registra o erro no log.

---

### 5. **db.py** — Conexões e Logs

**Responsabilidades:**

1. **Criar engines SQLAlchemy**
   - `get_source_engine()` → conecta ao banco origem
   - `get_dest_engine()` → conecta ao banco destino
   - Ambas usando URLs de `.env`

2. **Setup de logs**
   - `setup_logger(nome)` → cria arquivo `logs/nome.log`
   - Todos os pipelines, scheduler e refresh_mvs usam isso
   - Formato: `2026-09-27 06:00:15 INFO Iniciando pipeline...`

**Configuração (.env):**
```
SOURCE_DB_URL=postgresql+psycopg2://user:senha@host_origem:5432/db_origem
DEST_DB_URL=postgresql+psycopg2://user:senha@host_destino:5432/db_destino
```

---

## 🔄 Fluxo de Dados Completo

Exemplo: Executar às 6h da manhã.

```
[06:00:00] Scheduler acorda
           ↓
[06:00:01] Dispara main.py
           ├─ clientes.run()
           │  ├─ SELECT dw.mv_clientes FROM origem (45k linhas)
           │  ├─ DELETE FROM dw.mv_clientes (destino)
           │  ├─ INSERT INTO dw.mv_clientes (45k linhas novas)
           │  └─ Log: "45000 linhas inseridas em 5.2s"
           │
           ├─ estoque.run()
           │  ├─ SELECT dw.mv_estoque FROM origem (100k linhas)
           │  ├─ DELETE FROM dw.mv_estoque (destino)
           │  ├─ INSERT INTO dw.mv_estoque (100k linhas novas)
           │  └─ Log: "100000 linhas inseridas em 8.7s"
           │
           ├─ giro.run()
           │  ├─ SELECT dw.mv_giro FROM origem (últimos 3 dias = 50k linhas)
           │  ├─ DELETE FROM dw.mv_giro (últimos 3 dias)
           │  ├─ INSERT INTO dw.mv_giro (50k linhas novas)
           │  └─ Log: "50000 linhas inseridas em 6.1s"
           │
           └─ refresh_mvs.run()
              ├─ REFRESH public.mv_erp_lojas
              ├─ REFRESH public.mv_erp_skus
              ├─ REFRESH public.mv_erp_estoque_loja
              ├─ ... (9 views total)
              └─ Log: "9 MVs atualizadas em 12.3s"

[06:30:45] Pipeline completa. Total: 32s
           Scheduler volta a dormir
           Próximo disparo: 06:30:00

[06:30:00] Scheduler acorda de novo
           Repete o mesmo fluxo...
```

---

## 🔗 Dependências

### Bibliotecas Python (requirements.txt)

```
sqlalchemy>=2.0          # Framework pra queries SQL (abstrai diferenças entre bancos)
psycopg2-binary          # Driver PostgreSQL nativo (fala a linguagem que Postgres entende)
python-dotenv            # Lê arquivo .env (credenciais, horários, etc)
```

**Por que essas?**
- **SQLAlchemy:** Não precisa escrever SQL à mão, faz queries Python → SQL
- **psycopg2:** Conexão TCP direta ao Postgres, super rápido
- **dotenv:** Credenciais em arquivo `.env` fora do repositório (segurança)

### Dependências de Sistema

```
Python 3.8+              # Runtime
PostgreSQL 12+           # Bancos origem e destino
systemd (VPS)            # Gerenciar o daemon (auto-restart)
```

### Dependências de Acesso

```
Conectividade TCP:5432   # Porta padrão PostgreSQL
Acesso origem: read-only (SELECT)
Acesso destino: write (DELETE, INSERT)
Sem Traefik necessário   # Conexão TCP direto, não HTTP
```

---

## ⚙️ Como Funciona Internamente (Técnico)

### Execução de um Pipeline

```python
# 1. Conectar origem
with source_engine.connect() as src_conn:
    # 2. Ler dados
    rows = src_conn.execute(text(sql)).mappings().all()
    # mappings() = cada linha é um dicionário {"col1": val1, "col2": val2, ...}
    # all() = baixar tudo na memória (40-50k linhas = ~50MB, aceitável)

# 3. Conectar destino e começar transação
with dest_engine.begin() as dest_conn:
    # begin() = abre transação, faz commit no final, rollback se erro
    
    # 4. Limpar
    dest_conn.execute(text("DELETE FROM tabela"))
    
    # 5. Inserir tudo em lote (1 round-trip, não N inserts)
    dest_conn.execute(text("INSERT ... VALUES (...)"), rows)
    
    # 6. Se chegou aqui, commit automático
```

**Por que transação (`begin`)?**
- Se DELETE funciona mas INSERT falha, rollback faz DELETE voltar
- Garante que a tabela nunca fica em estado "meio carregada"

### Agendamento do Scheduler

```python
while True:
    now = datetime.now()  # ex: 06:15:30
    
    today_start = parse_time("06:00")  # 06:00
    today_end = parse_time("22:00")    # 22:00
    
    if now < today_start:
        # 05:00? Espera até 06:00
        sleep_secs = (today_start - now).total_seconds()
        time.sleep(sleep_secs)
        continue
    
    if now > today_end:
        # 23:00? Espera até amanhã 06:00
        tomorrow_start = (now + timedelta(days=1)).replace(hour=6, minute=0)
        sleep_secs = (tomorrow_start - now).total_seconds()
        time.sleep(sleep_secs)
        continue
    
    # Dentro da janela! Executa.
    try:
        run_all_pipelines()
    except Exception as e:
        logger.exception(e)  # Loga erro mas não morre
    
    # Calcula próximo disparo
    next_run = now + timedelta(minutes=30)
    if next_run > today_end:
        # Próximo seria depois do fim da janela, vai pra amanhã
        sleep_secs = (tomorrow_start - now).total_seconds()
    else:
        sleep_secs = (next_run - now).total_seconds()
    
    time.sleep(sleep_secs)
```

---

## 📊 Exemplo de Execução Real

```
$ cat logs/scheduler.log

2026-09-27 06:00:00 INFO Scheduler iniciado: 06:00 - 22:00, intervalo 30 min
2026-09-27 06:00:01 INFO Iniciando execução da pipeline...
2026-09-27 06:00:02 INFO Iniciando pipeline clientes...
2026-09-27 06:00:10 INFO Lidas 45000 linhas na origem
2026-09-27 06:00:15 INFO Pipeline clientes concluído: 45000 linhas inseridas em 13.15s
2026-09-27 06:00:16 INFO Iniciando pipeline estoque...
2026-09-27 06:00:28 INFO Lidas 100000 linhas na origem
2026-09-27 06:00:40 INFO Pipeline estoque concluído: 100000 linhas inseridas em 24.12s
2026-09-27 06:00:41 INFO Iniciando pipeline giro (dias_carga=3)...
2026-09-27 06:00:50 INFO Lidas 50000 linhas na origem
2026-09-27 06:00:55 INFO Pipeline giro concluído: 50000 linhas inseridas em 14.23s
2026-09-27 06:00:56 INFO Iniciando refresh das materialized views...
2026-09-27 06:01:10 INFO ✓ public.mv_erp_lojas atualizada
2026-09-27 06:01:11 INFO ✓ public.mv_erp_skus atualizada
2026-09-27 06:01:12 INFO ✓ public.mv_erp_estoque_loja atualizada
2026-09-27 06:01:13 INFO ✓ public.mv_erp_vendas atualizada
2026-09-27 06:01:14 INFO ✓ public.mv_erp_clientes atualizada
2026-09-27 06:01:15 INFO ✓ public.mv_erp_historico_compras atualizada
2026-09-27 06:01:16 INFO ✓ public.mv_erp_vendedores atualizada
2026-09-27 06:01:17 INFO ✓ public.mv_erp_cliente_vendedor atualizada
2026-09-27 06:01:18 INFO ✓ public.mv_erp_titulos atualizada
2026-09-27 06:01:19 INFO Refresh concluído: 9 MVs atualizadas em 12.3s
2026-09-27 06:01:20 INFO Pipeline concluída com sucesso
2026-09-27 06:01:20 INFO Próxima execução em 06:31:20 (1800.0s)
```

**Interpretação:**
- Total: ~1min20s pra carga + refresh completo
- Próximo disparo: 06:31:20 (30 min depois)
- Tudo sucesso, zero erros

---

## 🐛 O Que Pode Dar Errado?

| Problema | Causa | Sintoma |
|----------|-------|---------|
| Credenciais erradas | `.env` com host/user/pass/db inválido | `could not connect to server` |
| Banco destino sem espaço | Disco cheio | `no space left on device` |
| View sem índice único | MV não tem `UNIQUE INDEX` | `REFRESH MATERIALIZED VIEW CONCURRENTLY` falha |
| Rede cai | Conexão TCP interrompida | `connection lost` |
| Scheduler morreu | systemd parou o serviço | Nenhuma execução agendada |

**Como debugar:**
```bash
# Ver último erro
tail -20 logs/*.log

# Ver se scheduler está rodando
ps aux | grep scheduler.py

# Ver status systemd
systemctl status etl-overlabel

# Testar conexão manual
psql "postgresql://user:pass@host:5432/db"
```

---

## 📈 Perguntas Frequentes

### P: Por que não usar Airflow/Prefect/Dagster?
**R:** Overkill pra uma aplicação simples. Scheduler Python puro é:
- Menos dependências (só SQLAlchemy + psycopg2)
- Mais fácil de debugar
- Menos recurso na VPS

### P: Por que não usar cron do servidor?
**R:** Porque:
- Cron precisa de acesso shell na VPS
- Scheduler Python é mais portável (funciona igual em qualquer SO)
- Mais fácil mudar horários sem mexer em crontab

### P: Quantos dados posso carregar?
**R:** 
- 195k linhas/execução (45k + 100k + 50k) funciona em ~1min20s
- Se aumentar 10x, levará ~13 min/execução
- Limite prático: até que caiba em memória (Python + dados)

### P: E se os bancos estão em datacenters diferentes?
**R:** Funciona igual, só será mais lento pela latência de rede.

### P: Preciso de backup?
**R:** Sim. Antes de primeira execução, faça snapshot do banco destino. Se algo der errado, restaurar é seguro.

---

## 🎓 Conclusão

Esta aplicação é um **ETL simples e direto**:
- **Extrai** dados de um banco PostgreSQL origem
- **Transforma** (mínimo — cópias diretas)
- **Carrega** em um banco destino PostgreSQL
- **Atualiza** views consumidoras
- **Agenda** tudo automaticamente

Nada de ferramentas complexas, nada de overhead. Código Python puro que funciona 24/7 em background na VPS.

---

**Versão:** 1.0  
**Escrito para:** Pessoas leigas em ETL e DevOps  
**Quando revisar:** Se adicionar novos pipelines ou mudar a arquitetura de agendamento
