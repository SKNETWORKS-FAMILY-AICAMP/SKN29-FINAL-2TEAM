class DocumentPipelineError(Exception):
    """Base error for the local Django/RunPod boundary."""


class PipelineConfigurationError(DocumentPipelineError):
    pass


class RunPodRequestError(DocumentPipelineError):
    pass


class RunPodResultError(DocumentPipelineError):
    pass


class DocumentNotReadyError(DocumentPipelineError):
    pass
