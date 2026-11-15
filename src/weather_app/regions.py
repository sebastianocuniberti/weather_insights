"""Preset city lists: continents and themed "analysis sets".

OpenWeatherMap's free API answers one city per request — there is no "give me a
whole continent" call. So a continent (or any set) here is a hand-picked list
of cities. Each analysis set is split into labelled groups, e.g. "Hot vs cold"
-> {"Hot": [...], "Cold": [...]}, so the analytics know which side each city is on.

Each set is fetched as one "batch". The client's rate limiter (55 requests per
minute) spreads the requests out, so even the ~195-city capitals set just works:
it simply takes a few minutes.
"""

CONTINENTS = {
    "Europe": ["Madrid,ES", "Venice,IT", "London,GB", "Paris,FR", "Berlin,DE",
               "Oslo,NO", "Athens,GR"],
    "Asia": ["Tokyo,JP", "Beijing,CN", "Mumbai,IN", "Dubai,AE", "Singapore,SG",
             "Seoul,KR", "Bangkok,TH"],
    "Africa": ["Cairo,EG", "Lagos,NG", "Nairobi,KE", "Johannesburg,ZA",
               "Casablanca,MA", "Addis Ababa,ET", "Dakar,SN"],
    "North America": ["New York,US", "Los Angeles,US", "Chicago,US", "Toronto,CA",
                      "Mexico City,MX", "Miami,US", "Vancouver,CA"],
    "South America": ["São Paulo,BR", "Buenos Aires,AR", "Lima,PE", "Bogotá,CO",
                      "Santiago,CL", "Rio de Janeiro,BR", "Caracas,VE"],
    "Oceania": ["Sydney,AU", "Melbourne,AU", "Auckland,NZ", "Perth,AU",
                "Brisbane,AU", "Wellington,NZ", "Suva,FJ"],
}

# Themed sets for specific analyses. Same structure as CONTINENTS: group -> cities.
ANALYSIS_SETS = {
    "Hot vs cold": {
        "Hot": ["Kuwait City,KW", "Riyadh,SA", "Dubai,AE", "Phoenix,US", "Las Vegas,US",
                "Khartoum,SD", "Niamey,NE", "Baghdad,IQ", "Jaipur,IN", "Alice Springs,AU",
                "Darwin,AU", "Aswan,EG"],
        "Cold": ["Reykjavik,IS", "Yakutsk,RU", "Norilsk,RU", "Murmansk,RU", "Tromsø,NO",
                 "Nuuk,GL", "Anchorage,US", "Fairbanks,US", "Yellowknife,CA",
                 "Ulaanbaatar,MN", "Harbin,CN", "Ushuaia,AR"],
    },
    "Humid vs dry": {
        "Humid": ["Singapore,SG", "Kuala Lumpur,MY", "Manila,PH", "Jakarta,ID",
                  "Ho Chi Minh City,VN", "Manaus,BR", "Belém,BR", "Kolkata,IN", "Dhaka,BD",
                  "Colombo,LK", "Houston,US", "Kinshasa,CD"],
        "Dry": ["Phoenix,US", "Las Vegas,US", "Riyadh,SA", "Alice Springs,AU",
                "Windhoek,NA", "Tehran,IR", "Kabul,AF", "Ouarzazate,MA", "Denver,US",
                "Salt Lake City,US", "La Paz,BO", "Lhasa,CN"],
    },
    # Mid-latitude cities (about 30-45°) on both sides of the equator: same distance
    # from the equator, opposite seasons.
    "Hemispheres": {
        "North": ["Madrid,ES", "Rome,IT", "Lisbon,PT", "Athens,GR", "Tokyo,JP",
                  "Beijing,CN", "New York,US", "San Francisco,US"],
        "South": ["Buenos Aires,AR", "Santiago,CL", "Montevideo,UY", "Cape Town,ZA",
                  "Sydney,AU", "Melbourne,AU", "Wellington,NZ", "Hobart,AU"],
    },
    "Spain vs Madrid": {
        "Madrid": ["Madrid,ES"],
        "Rest of Spain": ["Barcelona,ES", "Valencia,ES", "Seville,ES", "Zaragoza,ES",
                          "Málaga,ES", "Bilbao,ES", "Palma,ES", "Las Palmas,ES",
                          "Alicante,ES", "Córdoba,ES", "Valladolid,ES", "Granada,ES",
                          "A Coruña,ES", "Oviedo,ES", "Murcia,ES", "Santander,ES",
                          "Salamanca,ES"],
    },
}


# National capitals by continent ("City,CC"). Where a country's official and
# working capitals differ we use the one OpenWeatherMap knows best (e.g. Colombo).
# Some capitals' status is disputed; this list is for weather only, not politics.
WORLD_CAPITALS = {
    "Europe": [
        "Tirana,AL", "Andorra la Vella,AD", "Vienna,AT", "Minsk,BY", "Brussels,BE",
        "Sarajevo,BA", "Sofia,BG", "Zagreb,HR", "Nicosia,CY", "Prague,CZ", "Copenhagen,DK",
        "Tallinn,EE", "Helsinki,FI", "Paris,FR", "Berlin,DE", "Athens,GR", "Budapest,HU",
        "Reykjavik,IS", "Dublin,IE", "Rome,IT", "Pristina,XK", "Riga,LV", "Vaduz,LI",
        "Vilnius,LT", "Luxembourg,LU", "Valletta,MT", "Chisinau,MD", "Monaco,MC",
        "Podgorica,ME", "Amsterdam,NL", "Skopje,MK", "Oslo,NO", "Warsaw,PL", "Lisbon,PT",
        "Bucharest,RO", "Moscow,RU", "San Marino,SM", "Belgrade,RS", "Bratislava,SK",
        "Ljubljana,SI", "Madrid,ES", "Stockholm,SE", "Bern,CH", "Kyiv,UA", "London,GB",
    ],
    "Asia": [
        "Kabul,AF", "Yerevan,AM", "Baku,AZ", "Manama,BH", "Dhaka,BD", "Thimphu,BT",
        "Bandar Seri Begawan,BN", "Phnom Penh,KH", "Beijing,CN", "Tbilisi,GE",
        "New Delhi,IN", "Jakarta,ID", "Tehran,IR", "Baghdad,IQ", "Jerusalem,IL",
        "Tokyo,JP", "Amman,JO", "Astana,KZ", "Kuwait City,KW", "Bishkek,KG",
        "Vientiane,LA", "Beirut,LB", "Kuala Lumpur,MY", "Male,MV", "Ulaanbaatar,MN",
        "Naypyidaw,MM", "Kathmandu,NP", "Pyongyang,KP", "Muscat,OM", "Islamabad,PK",
        "Ramallah,PS", "Manila,PH", "Doha,QA", "Riyadh,SA", "Singapore,SG", "Seoul,KR",
        "Colombo,LK", "Damascus,SY", "Taipei,TW", "Dushanbe,TJ", "Bangkok,TH", "Dili,TL",
        "Ankara,TR", "Ashgabat,TM", "Abu Dhabi,AE", "Tashkent,UZ", "Hanoi,VN", "Sanaa,YE",
    ],
    "Africa": [
        "Algiers,DZ", "Luanda,AO", "Porto-Novo,BJ", "Gaborone,BW", "Ouagadougou,BF",
        "Gitega,BI", "Praia,CV", "Yaounde,CM", "Bangui,CF", "N'Djamena,TD", "Moroni,KM",
        "Kinshasa,CD", "Brazzaville,CG", "Yamoussoukro,CI", "Djibouti,DJ", "Cairo,EG",
        "Malabo,GQ", "Asmara,ER", "Mbabane,SZ", "Addis Ababa,ET", "Libreville,GA",
        "Banjul,GM", "Accra,GH", "Conakry,GN", "Bissau,GW", "Nairobi,KE", "Maseru,LS",
        "Monrovia,LR", "Tripoli,LY", "Antananarivo,MG", "Lilongwe,MW", "Bamako,ML",
        "Nouakchott,MR", "Port Louis,MU", "Rabat,MA", "Maputo,MZ", "Windhoek,NA",
        "Niamey,NE", "Abuja,NG", "Kigali,RW", "Sao Tome,ST", "Dakar,SN", "Victoria,SC",
        "Freetown,SL", "Mogadishu,SO", "Pretoria,ZA", "Juba,SS", "Khartoum,SD",
        "Dodoma,TZ", "Lome,TG", "Tunis,TN", "Kampala,UG", "Lusaka,ZM", "Harare,ZW",
    ],
    "North America": [
        "Saint John's,AG", "Nassau,BS", "Bridgetown,BB", "Belmopan,BZ", "Ottawa,CA",
        "San Jose,CR", "Havana,CU", "Roseau,DM", "Santo Domingo,DO", "San Salvador,SV",
        "Saint George's,GD", "Guatemala City,GT", "Port-au-Prince,HT", "Tegucigalpa,HN",
        "Kingston,JM", "Mexico City,MX", "Managua,NI", "Panama City,PA", "Basseterre,KN",
        "Castries,LC", "Kingstown,VC", "Port of Spain,TT", "Washington,US",
    ],
    "South America": [
        "Buenos Aires,AR", "Sucre,BO", "Brasilia,BR", "Santiago,CL", "Bogota,CO",
        "Quito,EC", "Georgetown,GY", "Asuncion,PY", "Lima,PE", "Paramaribo,SR",
        "Montevideo,UY", "Caracas,VE",
    ],
    "Oceania": [
        "Canberra,AU", "Suva,FJ", "Tarawa,KI", "Majuro,MH", "Palikir,FM", "Yaren,NR",
        "Wellington,NZ", "Melekeok,PW", "Port Moresby,PG", "Apia,WS", "Honiara,SB",
        "Nuku'alofa,TO", "Funafuti,TV", "Port Vila,VU",
    ],
}

# All sets, continents first, the big capitals set last. Each one is fetched as a
# separate batch; the client's rate limiter spreads a big batch over several minutes.
CITY_SETS = {"Continents": CONTINENTS, **ANALYSIS_SETS, "World capitals": WORLD_CAPITALS}

# ISO country code -> continent. Covers the presets plus common extra cities
# a user might add; anything else is grouped under "Other".
_COUNTRY_TO_CONTINENT = {
    # Europe
    **dict.fromkeys(
        ["ES", "IT", "GB", "FR", "DE", "NO", "GR", "PT", "NL", "BE", "CH", "AT", "SE",
         "DK", "FI", "IE", "PL", "CZ", "HU", "RO", "HR", "IS", "UA", "RU", "TR", "LU",
         "SK", "SI", "BG", "RS", "EE", "LV", "LT", "MT", "CY", "MC", "AD"], "Europe"),
    # Asia
    **dict.fromkeys(
        ["JP", "CN", "IN", "AE", "SG", "KR", "TH", "ID", "MY", "PH", "VN", "PK", "BD",
         "SA", "QA", "IL", "HK", "TW", "KZ", "IR", "IQ", "LK", "NP", "JO", "LB", "KW",
         "MN", "AF"],
        "Asia"),
    # Africa
    **dict.fromkeys(
        ["EG", "NG", "KE", "ZA", "MA", "ET", "SN", "GH", "TZ", "DZ", "TN", "UG", "AO",
         "CI", "CM", "ZW", "RW", "MU", "SD", "NE", "CD", "NA"], "Africa"),
    # North America (incl. Central America & Caribbean)
    **dict.fromkeys(
        ["US", "CA", "MX", "CU", "GT", "CR", "PA", "DO", "JM", "PR", "HN", "SV", "NI",
         "BS", "GL"], "North America"),
    # South America
    **dict.fromkeys(["BR", "AR", "PE", "CO", "CL", "VE", "EC", "UY", "PY", "BO"],
                    "South America"),
    # Oceania
    **dict.fromkeys(["AU", "NZ", "FJ", "PG", "WS", "TO"], "Oceania"),
}

# Every capital's country belongs to the continent it is listed under.
for _continent, _cities in WORLD_CAPITALS.items():
    for _city in _cities:
        _COUNTRY_TO_CONTINENT.setdefault(_city.rsplit(",", 1)[1], _continent)


def continent_of(country_code):
    """'ES' -> 'Europe'; unknown or missing codes -> 'Other'."""
    if not isinstance(country_code, str):
        return "Other"
    return _COUNTRY_TO_CONTINENT.get(country_code.strip().upper(), "Other")


def cities_for(continents):
    """All preset cities for the given continent names ('all' = every continent)."""
    if continents == "all" or continents == ["all"]:
        continents = list(CONTINENTS)
    unknown = [c for c in continents if c not in CONTINENTS]
    if unknown:
        raise ValueError(f"Unknown continent(s): {', '.join(unknown)}. "
                         f"Choose from: {', '.join(CONTINENTS)}.")
    return [city for name in continents for city in CONTINENTS[name]]


def set_cities(set_name):
    """Unique cities in one set, in order: set_cities("Hot vs cold") -> [...24 cities]."""
    if set_name not in CITY_SETS:
        raise ValueError(f"Unknown set: {set_name}. Choose from: {', '.join(CITY_SETS)}.")
    seen, out = set(), []
    for cities in CITY_SETS[set_name].values():
        for city in cities:
            if city.lower() not in seen:
                seen.add(city.lower())
                out.append(city)
    return out


def plan_batches(set_names):
    """One batch per set, skipping cities an earlier batch already fetches.

    Returns [(set_name, [cities]), ...]. A city in two sets (e.g. Madrid) is
    fetched once; the analysis still finds it in both sets afterwards.
    """
    seen, batches = set(), []
    for name in set_names:
        batch = [c for c in set_cities(name) if c.lower() not in seen]
        seen.update(c.lower() for c in batch)
        if batch:
            batches.append((name, batch))
    return batches


def group_lookup(set_name):
    """Map (city, country) in lower case -> group label for one set.

    "Seville,ES" in group "Rest of Spain" becomes ("seville", "es") -> "Rest of Spain",
    which is how logged rows (city + country columns) are matched back to groups.
    """
    lookup = {}
    for group, cities in CITY_SETS[set_name].items():
        for city in cities:
            name, _, country = city.partition(",")
            lookup[(name.strip().lower(), country.strip().lower())] = group
    return lookup
