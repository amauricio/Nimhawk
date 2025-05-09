import { Button, Modal, Text, Group, Switch, Box, Loader, Alert, Progress, Select, Divider, Paper, Stack, Title, Badge, ThemeIcon, ScrollArea, useMantineTheme } from "@mantine/core"
import { FaHammer, FaFileDownload, FaPlus, FaFolder, FaCheckCircle, FaExclamationTriangle, FaTrash, FaExclamationCircle } from "react-icons/fa"
import { buildImplant, endpoints } from "../../modules/nimplant";
import { Dispatch, SetStateAction, useState, useEffect, useCallback } from "react";
import { notifications } from '@mantine/notifications';
import Payload from "./BuildImplant/Payload";
import Workspace from "./BuildImplant/Workspace";
import DebugOption from "./BuildImplant/DebugOption";
interface IProps {
    modalOpen: boolean;
    setModalOpen: Dispatch<SetStateAction<boolean>>;
}

function BuildImplantModal({ modalOpen, setModalOpen }: IProps) {
    const theme = useMantineTheme();
    const [isDebug, setIsDebug] = useState(false);
    const [isBuilding, setIsBuilding] = useState(false);
    const [buildResult, setBuildResult] = useState<any>(null);
    const [buildId, setBuildId] = useState<string | null>(null);
    const [buildStatus, setBuildStatus] = useState<any>(null);
    const [error, setError] = useState<string | null>(null);

    // Workspace related states
    const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
    const [selectedWorkspace, setSelectedWorkspace] = useState<string | null>(null);


    // Load workspaces when modal opens
    useEffect(() => {
        if (modalOpen) {
            fetchWorkspaces();
        }
    }, [modalOpen]);

    // Fetch workspaces from the server
    const fetchWorkspaces = async () => {
        try {
            // Obtain token from localStorage
            const token = localStorage.getItem('auth_token');

            const response = await fetch(`${endpoints.workspaces}`, {
                headers: {
                    'Content-Type': 'application/json',
                    ...(token ? { 'Authorization': `Bearer ${token}` } : {})
                }
            });

            if (response.ok) {
                const data = await response.json();
                console.log("Fetched workspaces:", data);
                setWorkspaces(data);
            } else {
                console.error("Error fetching workspaces:", await response.text());
            }
        } catch (err) {
            console.error("Error fetching workspaces:", err);
        }
    };



    // Poll for build status when buildId is available
    useEffect(() => {
        if (!buildId) return;

        const checkBuildStatus = async () => {
            try {
                // Obtain token from localStorage
                const token = localStorage.getItem('auth_token');

                const response = await fetch(`${endpoints.build}/status/${buildId}`, {
                    headers: {
                        'Content-Type': 'application/json',
                        ...(token ? { 'Authorization': `Bearer ${token}` } : {})
                    }
                });
                const status = await response.json();

                setBuildStatus(status);

                if (status.status === 'completed') {
                    setIsBuilding(false);
                    setBuildResult(status);
                } else if (status.status === 'failed') {
                    setIsBuilding(false);
                    setError(status.error || "Compilation failed. Check the logs for more details.");
                } else {
                    // Continue polling
                    setTimeout(checkBuildStatus, 2000);
                }
            } catch (err) {
                console.error("Error checking build status:", err);
                setTimeout(checkBuildStatus, 5000);
            }
        };

        checkBuildStatus();
    }, [buildId]);

    const handleBuild = async () => {
        setIsBuilding(true);
        setError(null);
        setBuildResult(null);
        setBuildStatus(null);

        try {
            // Call buildImplant with workspace parameter
            buildImplant(isDebug, (data) => {
                if (data && data.build_id) {
                    setBuildId(data.build_id);
                } else {
                    setIsBuilding(false);
                    setError("Failed to start build process");
                }
            }, selectedWorkspace);
        } catch (err) {
            console.error("Error starting build:", err);
            setIsBuilding(false);
            setError("Failed to start build process. Check the connection to the server.");
        }
    };

    const handleClose = () => {
        setModalOpen(false);
        setIsBuilding(false);
        setBuildResult(null);
        setBuildStatus(null);
        setBuildId(null);
        setError(null);
        setSelectedWorkspace(null);
        setWorkspaces([]);
    };

    const handleDownload = () => {
        if (buildResult && buildResult.download_url) {
            // Get the authentication token from localStorage
            const token = localStorage.getItem('auth_token');

            // Include the token as a URL parameter for authentication
            const downloadUrl = `${endpoints.server.replace('/api/server', '')}${buildResult.download_url}?token=${token}`;

            window.open(downloadUrl, '_blank');
        }
    };

    // Calculate progress information
    const getProgressInfo = () => {
        if (!buildStatus) return "Starting compilation...";
        return buildStatus.progress || "Compiling implants...";
    };

    return (
        <>

            {/* Main modal to build implants */}
            <Modal
                opened={modalOpen}
                onClose={handleClose}
                title={<Title order={4}>Build Implants</Title>}
                centered
                size="lg"
                radius="md"
                padding="xl"
                styles={{
                    header: {
                        backgroundColor: theme.colors.gray[0],
                        borderBottom: `1px solid ${theme.colors.gray[2]}`,
                        padding: '15px 20px'
                    },
                    body: { padding: '20px' },
                }}
            >
                <Stack>
                    <Text size="sm" color="dimmed">
                        This process will compile the complete implant package (EXE, DLL, and shellcode).
                        Compilation can take several minutes, especially the first time.
                    </Text>

                    <DebugOption 
                        disabled={isBuilding || buildResult !== null} 
                        onCheckedChange={setIsDebug} />

                    <Workspace
                        items={workspaces}
                        disabled={isBuilding || buildResult !== null}
                        onError={setError} />

                    {/* <Payload /> */}
                    {/*soon */}

                    {error && (
                        <Alert
                            color="red"
                            title="Error"
                            icon={<FaExclamationTriangle />}
                            radius="md"
                        >
                            {error}
                        </Alert>
                    )}

                    {isBuilding && (
                        <Paper p="md" radius="md" withBorder shadow="sm">
                            <Stack>
                                <Group justify="center" style={{ width: '100%' }}>
                                    <Loader size="sm" color={isDebug ? "orange" : "dark"} />
                                    <Text fw={500} color="dark" ta="center">{getProgressInfo()}</Text>
                                    <Loader size="sm" color={isDebug ? "orange" : "dark"} />
                                </Group>
                                <Progress
                                    animated
                                    value={100}
                                    color={isDebug ? "orange" : "dark"}
                                    size="md"
                                    radius="xl"
                                    striped
                                />
                                <Group justify="center" style={{ width: '100%' }}>
                                    <Text size="xs" color="dimmed">
                                        This process may take several minutes...
                                    </Text>
                                </Group>
                            </Stack>
                        </Paper>
                    )}

                    {buildResult && buildResult.status === 'completed' && (
                        <Paper p="md" radius="md" withBorder shadow="sm">
                            <Stack>
                                <Group>
                                    <ThemeIcon color={isDebug ? "orange" : "dark"} size="lg" radius="xl">
                                        <FaCheckCircle />
                                    </ThemeIcon>
                                    <Title order={5} style={{ color: isDebug ? theme.colors.orange[7] : theme.colors.dark[7] }}>Compilation Successful</Title>
                                </Group>

                                <Divider />

                                <Text size="sm" fw={500}>Generated files:</Text>
                                <ScrollArea style={{ height: 120 }} offsetScrollbars scrollbarSize={8}>
                                    {buildResult.files && buildResult.files.map((file: string, index: number) => (
                                        <Box
                                            key={index}
                                            p="xs"
                                            mb={5}
                                            style={{
                                                fontFamily: 'monospace',
                                                backgroundColor: theme.colors.gray[0],
                                                borderRadius: 4,
                                                fontSize: '0.85rem'
                                            }}
                                        >
                                            {file}
                                        </Box>
                                    ))}
                                </ScrollArea>
                            </Stack>
                        </Paper>
                    )}

                    <Divider my="sm" />

                    <Group justify="center">
                        {!buildResult ? (
                            <Button
                                onClick={handleBuild}
                                leftSection={<FaHammer />}
                                disabled={isBuilding}
                                color={isDebug ? "orange" : "dark"}
                                size="md"
                                fullWidth
                                radius="md"
                                styles={{
                                    root: {
                                        boxShadow: theme.shadows.sm,
                                        transition: 'all 0.3s ease',
                                        '&:hover': {
                                            transform: 'translateY(-2px)',
                                            boxShadow: theme.shadows.md
                                        }
                                    }
                                }}
                            >
                                {isBuilding ? "Compiling..." : "Build Implants"}
                                {isDebug && !isBuilding && <Badge ml="xs" size="sm" color="orange">Debug</Badge>}
                            </Button>
                        ) : (
                            <Button
                                onClick={handleDownload}
                                leftSection={<FaFileDownload />}
                                color={isDebug ? "orange" : "dark"}
                                size="md"
                                fullWidth
                                radius="md"
                                styles={{
                                    root: {
                                        boxShadow: theme.shadows.sm,
                                        transition: 'all 0.3s ease',
                                        '&:hover': {
                                            transform: 'translateY(-2px)',
                                            boxShadow: theme.shadows.md
                                        }
                                    }
                                }}
                            >
                                Download implants
                            </Button>
                        )}
                    </Group>
                </Stack>
            </Modal>
        </>
    )
}

export default BuildImplantModal 