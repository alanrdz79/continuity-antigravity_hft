import asyncio
from orquestadores_principales.HFT_GALO import telegram, ciclo_escaneo_hft, memoria_hft
from continuitis.financiero import MotorInteresCompuesto

def test():
    print("Testing CB")
    cb = MotorInteresCompuesto.verificar_circuit_breakers(40, 100)
    print("40, 100:", cb)
    
    cb = MotorInteresCompuesto.verificar_circuit_breakers(39, 100)
    print("39, 100:", cb)

    cb = MotorInteresCompuesto.verificar_circuit_breakers(80, 100)
    print("80, 100:", cb)
    
    cb = MotorInteresCompuesto.verificar_circuit_breakers(81, 100)
    print("81, 100:", cb)

    stake = MotorInteresCompuesto.calcular_stake_hft(500, 0.05, 2.0, 0.25, 3)
    print("Stake racha=3:", stake)
    
    stake = MotorInteresCompuesto.calcular_stake_hft(500, 0.05, 2.0, 0.25, 2)
    print("Stake racha=2:", stake)

test()
