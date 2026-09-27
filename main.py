from pipelines import clientes, estoque, giro
import refresh_mvs

if __name__ == "__main__":
    for pipeline in (clientes, estoque, giro):
        pipeline.run()

    refresh_mvs.run()
