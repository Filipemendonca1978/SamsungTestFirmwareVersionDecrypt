# Samsung Test Firmware Version Decryption Tool
## To run:

### Normal mode:

```bash
./run.sh model csc
```

#### Example:

```bash
./run.sh SM-A156M ZTO
```

### Custom firmware info mode:
```python
python samsung_test_firmware_decrypt.py (args)
```

### Supported arguments:
```text
--ap - AP (Application Processor) prefix (e.g., UB for M variant, ZTO Country Code)
--cscp - CSC (Country Service Code) prefix (e.g., OWO for ZTO Country Code)
--modem - CP (Core Processor/Modem) Prefix (e.g., UB for M variant, ZTO Country Code)
--bls - BootLoader's SW Rev bit's range start (e.g., 7)
--ble - BootLoader's SW Rev bit's range end (e.g., 8)
--sup - Major update version's range start (e.g., A)
--eup - Major update version's range end (e.g., B)
--sy - Start year's range start (e.g., W (2023))
--ey - Eng year's range start (e.g., Z (2026))
--output - Firmware's JSON output file dir/name (e.g., ./firmware.json)
--model - Model's name (e.g., SM-A156M) (can be used without the other extensions)
--csc - Country Service Code (e.g., ZTO) (can be used without the other extensions)
```

#### More examples:
```python
python samsung_test_firmware_decrypt.py --ap DX --cscp OWO --modem UB --bls 0 --ble 1 --sup A --eup B --sy W --ey X --output firmware.json --model SM-A156M --csc ZTO
python samsung_test_firmware_decrypt.py --model SM-A156M --csc ZTO
```

This is a fork, all the credits go to the original author
