"""Dummy master data for the ORBIT simulation. All insurers and dealers are fictional."""

INSURERS = {
    # code: (name, OD-rate multiplier vs. base, claim settlement days)
    "SGI": ("Suraksha General Insurance", 1.00, 9),
    "KVI": ("Kavach Insurance", 0.94, 12),
    "NBG": ("Nirbhay General", 1.06, 7),
    "ARA": ("Aarohan Assurance", 0.97, 10),
    "SHG": ("Sahyog General", 1.10, 6),
}

# OEM -> models: (model, cc, ex-showroom price in Rs.)
OEMS = {
    "Royal Enfield": [("Hunter 350", 349, 150000), ("Classic 350", 349, 193000),
                      ("Bullet 350", 349, 174000), ("Himalayan 450", 452, 285000),
                      ("Interceptor 650", 648, 303000)],
    "Hero MotoCorp": [("Splendor Plus", 97, 76000), ("Xtreme 160R", 163, 128000),
                      ("Xpulse 200", 199, 147000)],
    "TVS Motor": [("Jupiter 110", 109, 78000), ("Raider 125", 124, 95000),
                  ("Apache RTR 160", 159, 123000)],
    "Bajaj Auto": [("Pulsar N160", 164, 131000), ("Dominar 400", 373, 231000),
                   ("Platina 110", 115, 71000)],
    "Honda 2W": [("Activa 6G", 110, 79000), ("Shine 125", 124, 84000),
                 ("Hness CB350", 348, 210000)],
}

# dealer code: (name, OEM, city, (lat, lon))
DEALERS = {
    "RE-DEL-01": ("Rajdhani Royal Motors", "Royal Enfield", "New Delhi", (28.61, 77.21)),
    "RE-NOI-02": ("Thunder Bikes Noida", "Royal Enfield", "Noida", (28.54, 77.39)),
    "RE-LKO-03": ("Awadh Enfield House", "Royal Enfield", "Lucknow", (26.85, 80.95)),
    "RE-CHD-04": ("Hillside Riders", "Royal Enfield", "Chandigarh", (30.73, 76.78)),
    "HM-DEL-01": ("Capital Hero Wheels", "Hero MotoCorp", "New Delhi", (28.65, 77.23)),
    "HM-LKO-02": ("Gomti Hero Motors", "Hero MotoCorp", "Lucknow", (26.87, 80.99)),
    "TV-GGN-01": ("Cyber City TVS", "TVS Motor", "Gurugram", (28.46, 77.03)),
    "TV-JAI-02": ("Pink City TVS", "TVS Motor", "Jaipur", (26.91, 75.79)),
    "BA-DEL-01": ("Yamuna Bajaj", "Bajaj Auto", "New Delhi", (28.70, 77.10)),
    "BA-KNP-02": ("Ganga Bajaj Kanpur", "Bajaj Auto", "Kanpur", (26.45, 80.33)),
    "HO-NOI-01": ("Sector 18 Honda", "Honda 2W", "Noida", (28.57, 77.32)),
    "HO-DDN-02": ("Doon Honda Wings", "Honda 2W", "Dehradun", (30.32, 78.03)),
}

FIRST = ["Aman", "Rohit", "Priya", "Karan", "Neha", "Vikram", "Sana", "Arjun", "Meera", "Rahul",
         "Pooja", "Imran", "Simran", "Deepak", "Ankit", "Ritu", "Manish", "Kavya", "Sahil", "Tanvi"]
LAST = ["Sharma", "Verma", "Singh", "Gupta", "Khan", "Yadav", "Mehta", "Rawat", "Joshi", "Kapoor"]
GARAGES = ["Dealer workshop", "Other dealer", "Outside garage"]


def model_info(oem, model):
    for m, cc, price in OEMS[oem]:
        if m == model:
            return cc, price
    raise KeyError(model)
