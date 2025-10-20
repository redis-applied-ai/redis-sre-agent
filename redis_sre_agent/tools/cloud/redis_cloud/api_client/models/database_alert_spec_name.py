from enum import Enum


class DatabaseAlertSpecName(str, Enum):
    CONNECTIONS_LIMIT = "connections-limit"
    DATASETS_SIZE = "datasets-size"
    DATASET_SIZE = "dataset-size"
    LATENCY = "latency"
    SYNCSOURCE_ERROR = "syncsource-error"
    SYNCSOURCE_LAG = "syncsource-lag"
    THROUGHPUT_HIGHER_THAN = "throughput-higher-than"
    THROUGHPUT_LOWER_THAN = "throughput-lower-than"

    def __str__(self) -> str:
        return str(self.value)
