import ee
import config


def get_landsat_thermal(master_crs):
    """
    Get Landsat 8/9 thermal data as per-image LST values.

    Args:
        master_crs (ee.Projection): Master CRS from Sentinel-2.
    Returns:
        collection (ee.ImageCollection): Per-image images with LST (Celsius).
        metadata (dict): Metadata about the collection.
    """

    try:
        # Landsat 9 (newer) - before filtering
        l9_raw = (
            ee.ImageCollection("LANDSAT/LC09/C02/T1_L2")
            .filterBounds(config.ROI)
            .filterDate(config.START_DATE, config.END_DATE)
        )

        # Landsat 8 (more data available) - before filtering
        l8_raw = (
            ee.ImageCollection("LANDSAT/LC08/C02/T1_L2")
            .filterBounds(config.ROI)
            .filterDate(config.START_DATE, config.END_DATE)
        )

        landsat_raw = l9_raw.merge(l8_raw)
        total_count = landsat_raw.size().getInfo()

        # Calculate cloud coverage statistics BEFORE filtering. Pull
        # the per-image list too so downstream reporting can build a
        # "threshold sensitivity" counterfactual without re-querying
        # GEE.
        print("[Landsat] Calculating cloud coverage statistics...")
        cloud_stats = (
            landsat_raw.aggregate_stats("CLOUD_COVER").getInfo()
            if total_count > 0
            else {}
        )
        cloud_per_image = []
        if total_count > 0:
            try:
                cloud_per_image = (
                    landsat_raw.aggregate_array("CLOUD_COVER").getInfo() or []
                )
            except Exception as e:
                print(f"[Landsat] Warning: could not fetch per-image cloud array: {e}")

        # Calculate QA mask statistics
        print("[Landsat] Calculating QA mask statistics...")

        def compute_qa_masked_fraction(image):
            qa = image.select("QA_PIXEL")
            # Pixels with cloud or cloud shadow bits set
            cloud_mask = qa.bitwiseAnd(1 << 3).eq(0).And(qa.bitwiseAnd(1 << 4).eq(0))

            # Fraction of MASKED pixels (inverted mask)
            stats = cloud_mask.Not().reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=config.ROI,
                scale=90,  # Coarser scale for speed
                maxPixels=1e9,
                bestEffort=True,
            )

            masked_fraction = ee.Number(stats.get("QA_PIXEL", 0)).multiply(100)
            return image.set("qa_masked_fraction", masked_fraction)

        landsat_with_qa = (
            landsat_raw.map(compute_qa_masked_fraction)
            if total_count > 0
            else landsat_raw
        )
        qa_stats = (
            landsat_with_qa.aggregate_stats("qa_masked_fraction").getInfo()
            if total_count > 0
            else {}
        )

        # Apply cloud filter
        l9 = l9_raw.filter(ee.Filter.lt("CLOUD_COVER", config.CLOUD_THRESHOLD_LANDSAT))
        l8 = l8_raw.filter(ee.Filter.lt("CLOUD_COVER", config.CLOUD_THRESHOLD_LANDSAT))

        landsat = l9.merge(l8)
        count = landsat.size().getInfo()
        discarded_count = total_count - count

        if count == 0:
            # Genuinely empty — do not fabricate a -9999 sentinel image. That
            # got merged downstream as NaN, which looks identical to "cloud-
            # masked pixel" and hid the fact that the source had no data at
            # all for this ROI/window.
            print(
                f"[Landsat] No thermal data in {config.START_DATE}..{config.END_DATE} — "
                "LST will be absent from the output."
            )
            return ee.ImageCollection([]), {
                "source": "Landsat 8/9",
                "collection": "LANDSAT/LC08/C02/T1_L2 + LC09",
                "image_count": 0,
                "total_images": total_count,
                "available": False,
                "reason": "No Landsat 8/9 scenes pass filters for this ROI/window.",
                "date_range": f"{config.START_DATE} to {config.END_DATE}",
                "bands": ["LST"],
            }

        print(f"Found {count} Landsat images for thermal processing")

        # Convert thermal band to Celsius + apply QA mask + reproject
        def process_image(image):
            # ST_B10 in Landsat Collection 2 L2, scale factor: 0.00341802 + offset: 149.0
            lst_kelvin = image.select("ST_B10").multiply(0.00341802).add(149.0)
            lst_celsius = lst_kelvin.subtract(273.15)

            qa = image.select("QA_PIXEL")
            cloud_mask = qa.bitwiseAnd(1 << 3).eq(0).And(qa.bitwiseAnd(1 << 4).eq(0))

            # Note: copyProperties() returns ee.Element, so cast back to ee.Image
            return (
                ee.Image(lst_celsius.updateMask(cloud_mask).rename("LST"))
                .set("system:time_start", image.date().millis())
                .reproject(crs=master_crs, scale=config.TARGET_SCALE)
            )

        collection = landsat.map(process_image)

        metadata = {
            "source": "Landsat 8/9",
            "collection": "LANDSAT/LC08/C02/T1_L2 + LC09",
            "image_count": count,
            "total_images": total_count,
            "discarded_images": discarded_count,
            "discarded_pct": (
                (discarded_count / total_count * 100) if total_count > 0 else 0
            ),
            "discard_reason": f"Cloud threshold (>{config.CLOUD_THRESHOLD_LANDSAT}%)",
            "date_range": f"{config.START_DATE} to {config.END_DATE}",
            "bands": ["LST"],
            "cloud_coverage": {
                "mean": cloud_stats.get("mean", 0),
                "min": cloud_stats.get("min", 0),
                "max": cloud_stats.get("max", 0),
                "stddev": cloud_stats.get("stdDev", 0),
            },
            "cloud_threshold_used": config.CLOUD_THRESHOLD_LANDSAT,
            "cloud_per_image_pct": cloud_per_image,
            "qa_masked": {
                "mean": qa_stats.get("mean", 0),
                "min": qa_stats.get("min", 0),
                "max": qa_stats.get("max", 0),
                "stddev": qa_stats.get("stdDev", 0),
            },
        }

        return collection, metadata

    except Exception as e:
        print(f"[Landsat] Error processing thermal data: {e}. Returning empty.")
        return ee.ImageCollection([]), {
            "source": "Landsat 8/9",
            "image_count": 0,
            "available": False,
            "reason": f"Processing error: {e}",
            "date_range": f"{config.START_DATE} to {config.END_DATE}",
            "bands": ["LST"],
            "error": str(e),
        }
