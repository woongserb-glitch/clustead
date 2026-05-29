def distance_weight(distance):
    if distance <= 200:
        return 1.0
    elif distance <= 500:
        return 0.7
    elif distance <= 1000:
        return 0.4
    else:
        return 0.15