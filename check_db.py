import sqlite3
import pandas as pd

def check_db():
    conn = sqlite3.connect('C:/Users/alanr/AE_ecosistema/CONTINUITYEM/cerebrillum.db')
    
    print("--- ÚLTIMAS APUESTAS REGISTRADAS ---")
    try:
        df1 = pd.read_sql("SELECT * FROM apuestas_registro ORDER BY timestamp DESC LIMIT 5", conn)
        if df1.empty:
            print("No hay apuestas en apuestas_registro.")
        else:
            print(df1[['timestamp', 'liga_id', 'equipo_local', 'mercado', 'ev_predicho']].to_string())
    except Exception as e:
        print("Error al leer apuestas:", e)
        
    print("\n--- SCHEMA ETL_LOG ---")
    try:
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(etl_log)")
        cols = [r[1] for r in cur.fetchall()]
        print("Columnas en etl_log:", cols)
        
        df2 = pd.read_sql("SELECT * FROM etl_log ORDER BY timestamp DESC LIMIT 10", conn)
        print(df2.to_string())
    except Exception as e:
        print("Error al leer etl_log:", e)

    print("\n--- COLA PARTIDOS PENDIENTES ---")
    try:
        df3 = pd.read_sql("SELECT * FROM cola_partidos_pendientes ORDER BY fecha_partido ASC LIMIT 10", conn)
        print(df3)
    except Exception as e:
         print("Error:", e)
         
    conn.close()

if __name__ == '__main__':
    check_db()
