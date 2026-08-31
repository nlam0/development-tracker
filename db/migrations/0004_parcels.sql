-- One row per tax lot, from PLUTO (M3). Loads after study_areas /
-- study_area_bbls since parcels.neighborhood references study_areas(name).
CREATE TABLE parcels (
  bbl               CHAR(10) PRIMARY KEY,
  borough           SMALLINT NOT NULL,
  block             INTEGER NOT NULL,
  lot               INTEGER NOT NULL,
  address           TEXT,
  neighborhood      TEXT REFERENCES study_areas(name),
  latitude          DOUBLE PRECISION,
  longitude         DOUBLE PRECISION,
  geom              GEOMETRY(Point, 4326),
  zoning            TEXT,             -- zonedist1
  land_use          TEXT,             -- landuse code; label resolved via lookup
  lot_area          INTEGER,
  building_area     INTEGER,
  commercial_area   INTEGER,
  residential_area  INTEGER,
  units_residential INTEGER,
  units_total       INTEGER,
  num_buildings     INTEGER,
  num_floors        NUMERIC(5,2),
  year_built        SMALLINT,
  assessed_total    BIGINT,
  owner_name        TEXT,
  census_tract_2020 TEXT,             -- bct2020; joins ACS 2024 (Risk R11)
  census_tract_2010 TEXT,             -- ct2010;  joins ACS 2014 / 2019 (Risk R11)
  pluto_version     TEXT NOT NULL,    -- pinned to '26v2'; PLUTO is a versioned snapshot
  retrieved_at      TIMESTAMPTZ NOT NULL
);

CREATE INDEX parcels_geom_idx ON parcels USING GIST (geom);
CREATE INDEX parcels_neighborhood_idx ON parcels (neighborhood);
