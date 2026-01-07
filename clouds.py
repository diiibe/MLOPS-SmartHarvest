def cloudmask(image):
    """
    Function for cloud masking in Sentinel-2 using the QA60 band to identify clouds.
    """
    qa = image.select('QA60')
    cloudbit = 1 << 10
    cirrusbit = 1 << 11
    mask = qa.bitwiseAnd(cloudbit).eq(0).And(qa.bitwiseAnd(cirrusbit).eq(0))
    return image.updateMask(mask)