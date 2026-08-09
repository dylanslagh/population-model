"""Country outlines for the map.

Natural Earth, pinned to a tagged release rather than to `master`. The branch
moves; a shape that silently changes under a stored prediction is the same
class of problem as a data file that silently changes, and spec section 9's
whole argument is that the archive has to still mean something in decades.

Why two layers
--------------
`admin_0_countries` is the everyday world map: 242 shapes, one per country,
with overseas departments folded into their parent. It matches 228 of WPP's
237 countries and areas straight off.

`admin_0_map_units` is the same world cut finer: 265 shapes, where France is
split into metropolitan France plus Mayotte, Réunion, Guadeloupe, Martinique
and French Guiana, and the Netherlands into its European and Caribbean parts.
The UN counts those separately, so WPP has population figures for them.

Using map_units for everything would be worse, not better: it also splits the
United Kingdom into four, Belgium into three and Portugal into three, which
then have to be glued back together. So the countries layer is the base and
map_units is consulted only for the handful of places the base layer lacks.

The join key
------------
Natural Earth carries `UN_A3`, the UN's own M49 numeric code, and WPP's LocID
for a country IS that code. So this is a real key join, not name matching.
Name matching across 237 countries is how "Congo" becomes the wrong Congo.
"""

from __future__ import annotations

from dataclasses import dataclass

RELEASE = "v5.1.2"
SOURCE = "Natural Earth (naturalearthdata.com), public domain"
REPO = "https://github.com/nvkelso/natural-earth-vector"
_BASE = f"https://raw.githubusercontent.com/nvkelso/natural-earth-vector/{RELEASE}/geojson"

# Natural Earth's own scale names. 50m is the middle one: detailed enough that
# small island states exist, small enough to ship to a browser.
SCALE = "50m"


@dataclass(frozen=True)
class GeoLayer:
    key: str
    filename: str
    purpose: str
    approx_mb: int

    @property
    def url(self) -> str:
        return f"{_BASE}/{self.filename}"


LAYERS: dict[str, GeoLayer] = {
    layer.key: layer
    for layer in [
        GeoLayer(
            key="countries",
            filename=f"ne_{SCALE}_admin_0_countries.geojson",
            purpose="Base map: one shape per country, overseas departments folded in.",
            approx_mb=3,
        ),
        GeoLayer(
            key="map_units",
            filename=f"ne_{SCALE}_admin_0_map_units.geojson",
            purpose=(
                "Finer cut, consulted only for the territories the base layer "
                "folds into a parent but the UN counts separately."
            ),
            approx_mb=3,
        ),
    ]
}

# Properties that may carry a numeric UN M49 code, in the order to try them.
# UN_A3 is the authoritative one; the ISO numeric fields are a fallback for
# entries where Natural Earth left UN_A3 blank.
CODE_FIELDS = ("UN_A3", "ISO_N3_EH", "ISO_N3")
