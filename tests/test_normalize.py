from fortibugs.normalize import canonical_model, hardware_tags, model_core, normalize_category

CORES = ["60F", "61F", "90E", "91E", "400F", "1500D", "3700D", "4401F"]


def tags(text, category="System"):
    return hardware_tags(text, category, CORES)


def test_categories_are_merged():
    for name in ("Log & Report", "Log and Report", "Logging and reporting", "Log/Report"):
        assert normalize_category(name) == "Log & Report"
    assert normalize_category("Web-based Manager") == "GUI"
    assert normalize_category("FortiGate 6000 and 7000 platforms") == "FortiGate 6000/7000"
    assert normalize_category(None) == "Uncategorized"


def test_model_names():
    assert canonical_model("FGT-60D-POE") == "FG-60D-POE"
    assert canonical_model("FGR-70G-5G-Dual") == "FGR-70G-5G-DUAL"
    assert canonical_model("FS-108D") is None
    assert canonical_model("FG-VMXFG-VM64-XEN") is None
    assert model_core("FWF-60F-3G4G") == "60F"


def test_models_in_text():
    assert tags("Performance drop on FortiGate 4401F")[0] == ["4401F"]
    assert tags("Crash on FG-1500D and FG-3700D")[0] == ["1500D", "3700D"]
    assert tags("Issue on FortiGate-90E/91E")[0] == ["90E", "91E"]
    assert tags("Reboot on FGT60F")[0] == ["60F"]


def test_category_can_name_the_hardware():
    assert tags("Fan alarm", "FortiGate-90E/91E")[0] == ["90E", "91E"]


def test_unknown_cores_and_plain_numbers_are_ignored():
    assert tags("Reached 6000 sessions with 400F of margin")[:2] == ([], [])
    assert tags("FortiGate 9999Z is not a model")[0] == []


def test_families_and_asics():
    assert tags("ZTNA sync on FortiGate 6KF, 7KE")[1] == ["6000", "7000"]
    assert tags("Drops", "FortiGate 6000/7000")[1] == ["6000", "7000"]
    assert tags("Boot failure", "VM")[1] == ["VM"]
    assert tags("Audio cutouts on NP7 models")[2] == ["NP7"]
