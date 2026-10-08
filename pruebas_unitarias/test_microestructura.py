from continuitis.microestructura import CalculadorVWAP, AjustadorComisiones, EstrategiaMakerTaker
from continuitis.constantes import MB_COMMISSION_RATE

def test_calculador_vwap():
    libro = [
        {"odds": 2.50, "available-amount": 50.0},
        {"odds": 2.48, "available-amount": 100.0},
        {"odds": 2.45, "available-amount": 200.0},
    ]
    
    # Caso 1: Todo se llena en el primer nivel
    vwap, slippage, liquidez, niveles = CalculadorVWAP.calcular(libro, 30.0)
    assert vwap == 2.50
    assert slippage == 0.0
    assert niveles == 1
    
    # Caso 2: Se consumen dos niveles (50 a 2.50, 50 a 2.48)
    vwap, slippage, liquidez, niveles = CalculadorVWAP.calcular(libro, 100.0)
    assert vwap == 2.49  # (50*2.50 + 50*2.48) / 100 = (125 + 124) / 100 = 249 / 100
    assert niveles == 2
    
def test_ajustador_comisiones():
    cuota_bruta = 3.00
    # Matchbook cobra 2% sobre la ganancia neta (2.00)
    # Ganancia neta esperada = 2.00 * 0.98 = 1.96
    # Cuota neta efectiva = 1.96 + 1.00 = 2.96
    cuota_neta = AjustadorComisiones.cuota_neta(cuota_bruta, 0.02)
    assert round(cuota_neta, 2) == 2.96
    
    ev_bruto = 0.40 * 3.00 - 1.0  # +20%
    ev_neto = AjustadorComisiones.ev_neto(0.40, 3.00, 0.02) # 0.40 * 2.96 - 1.0 = +18.4%
    assert round(ev_neto, 3) == 0.184

def test_maker_taker_pre_match():
    # Pre-match -> taker
    decision = EstrategiaMakerTaker.decidir(
        in_running=False, es_pausa=False, ev_neto=0.05, 
        stake_kelly=100.0, liquidez_back=500.0, best_odds=2.00, side="back"
    )
    assert decision["modo"] == "taker"
    assert decision["odds_propuestas"] == 2.00
    
def test_maker_taker_in_play():
    # In-play -> maker (evita delay)
    decision = EstrategiaMakerTaker.decidir(
        in_running=True, es_pausa=False, ev_neto=0.05, 
        stake_kelly=100.0, liquidez_back=500.0, best_odds=2.00, side="back"
    )
    assert decision["modo"] == "maker"
    assert decision["odds_propuestas"] == 2.02

if __name__ == "__main__":
    test_calculador_vwap()
    test_ajustador_comisiones()
    test_maker_taker_pre_match()
    test_maker_taker_in_play()
    print("All tests passed!")
