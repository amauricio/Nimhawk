import { Select, Paper, Stack, Title, Button, Group, Badge, Text, useMantineTheme, Modal, Divider, ThemeIcon } from "@mantine/core"
import { useEffect, useState } from "react";
import { FaExclamationCircle, FaFolder, FaPlus, FaTrash } from "react-icons/fa";
import { endpoints } from "../../../modules/nimplant";
import { notifications } from "@mantine/notifications";

interface Workspace {
    id: number;
    workspace_uuid: string;
    workspace_name: string;
    creation_date: string;
}

interface WorkspaceProps {
    items: Workspace[];
    disabled: boolean;
    onDeleteWorkspace?: () => void;
    onCreateWorkspace?: () => void;
    onError?: (error: string) => void;  
}
function Workspace({ items, disabled, onDeleteWorkspace, onCreateWorkspace, onError }: WorkspaceProps) {
    const theme = useMantineTheme();

    const [workspaceToDelete, setWorkspaceToDelete] = useState<{ uuid: string, name: string } | null>(null);
    const [searchValue, setSearchValue] = useState('');
    const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
    // Add a new function to delete workspaces
    const handleDeleteWorkspace = (workspaceUuid: string, workspaceName: string) => {
        setWorkspaceToDelete({ uuid: workspaceUuid, name: workspaceName });
        setDeleteModalOpen(true);
    };
    const [selectedWorkspace, setSelectedWorkspace] = useState<string | null>(null);
    const [isCreatingWorkspace, setIsCreatingWorkspace] = useState(false);
    const [deleteModalOpen, setDeleteModalOpen] = useState(false);

    useEffect(() => {
        setWorkspaces(items);
    }, [items]);


    // Custom component for dropdown options
    const CustomSelectOption = ({ option }: { option: { label: string, uuid?: string } }) => {
        if (!option.uuid) return <div>{option.label}</div>;

        return (
            <Group justify="space-between" style={{ width: '100%' }}>
                <Text>{option.label}</Text>
                {option.uuid && option.uuid !== '' && (
                    <Button
                        variant="subtle"
                        color="red"
                        size="xs"
                        onClick={(e) => {
                            e.stopPropagation();
                            const workspace = workspaces.find(w => w.workspace_uuid === option.uuid);
                            if (workspace && option.uuid) {
                                handleDeleteWorkspace(option.uuid, workspace.workspace_name);
                            }
                        }}
                        title="Delete workspace"
                        disabled={disabled}
                        styles={{ root: { padding: '2px 6px', minWidth: 'auto' } }}
                    >
                        ✕
                    </Button>
                )}
            </Group>
        );
    };

    // Add function to confirm the deletion
    const confirmDeleteWorkspace = async () => {
        console.log("workspaceToDelete", workspaceToDelete);
        if (!workspaceToDelete) return;

        try {
            setDeleteModalOpen(false);

            // Get token from localStorage
            const token = localStorage.getItem('auth_token');

            const response = await fetch(`${endpoints.workspaces}/${workspaceToDelete.uuid}`, {
                method: 'DELETE',
                headers: {
                    'Content-Type': 'application/json',
                    ...(token ? { 'Authorization': `Bearer ${token}` } : {})
                }
            });

            if (response.ok) {
                // Show success notification
                notifications.show({
                    title: 'Success',
                    message: `Workspace "${workspaceToDelete.name}" deleted successfully`,
                    color: 'green',
                });

                // If the deleted workspace was the selected one, clear the selection
                if (selectedWorkspace === workspaceToDelete.uuid) {
                    setSelectedWorkspace(null);
                }
                
                //refresh the list of workspaces deleting the workspace from the list
                setWorkspaces(workspaces.filter(ws => ws.workspace_uuid !== workspaceToDelete.uuid));
                onDeleteWorkspace && onDeleteWorkspace();


            } else {
                const errorText = await response.text();
                console.error(`Error deleting workspace: ${errorText}`);
                notifications.show({
                    title: 'Error',
                    message: `Failed to delete workspace: ${errorText}`,
                    color: 'red',
                });
            }
        } catch (error) {
            console.error("Error deleting workspace:", error);
            notifications.show({
                title: 'Error',
                message: `Error deleting workspace: ${error instanceof Error ? error.message : String(error)}`,
                color: 'red',
            });
        } finally {
            setWorkspaceToDelete(null);
        }
    };


    // Prepare workspace data for Select component
    const workspaceSelectData = [
        { value: 'Default', label: 'Default (No Workspace)', uuid: '' },
        ...workspaces.filter(ws => ws.workspace_name !== 'Default').map(ws => ({
            value: ws.workspace_uuid,
            label: ws.workspace_name,
            uuid: ws.workspace_uuid
        }))
    ];
    const searchValueExists = workspaceSelectData.some(
        item => item.label.toLowerCase() === searchValue.toLowerCase()
    );

    // Handle workspace creation when no match is found
    function handleCreateFromSearch() {
        if (!searchValue.trim()) return;

        const workspaceName = searchValue;
        console.log("Attempting to create workspace from search:", workspaceName);

        // Store the name we're trying to create so we can keep showing the button
        const nameToCreate = searchValue;

        try {
            setIsCreatingWorkspace(true);

            // Make direct API call without using the createWorkspace function
            const token = localStorage.getItem('auth_token');

            // Use .then instead of async/await to avoid potential problems
            fetch(endpoints.workspaces, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    ...(token ? { 'Authorization': `Bearer ${token}` } : {})
                },
                body: JSON.stringify({ workspace_name: workspaceName })
            })
                .then(response => {
                    console.log(`Create workspace API response status: ${response.status}`);
                    return response.text().then(text => {
                        console.log(`Create workspace API response text:`, text);
                        if (!response.ok) {
                            throw new Error(`Server error: ${text}`);
                        }
                        return text;
                    });
                })
                .then(responseText => {
                    // Try to parse JSON response
                    let data;
                    try {
                        data = JSON.parse(responseText);
                        console.log("Parsed response data:", data);
                    } catch (e) {
                        console.error("Failed to parse JSON response:", e);
                        throw new Error("Invalid server response format");
                    }

                    // Show success notification
                    notifications.show({
                        title: 'Success',
                        message: `Workspace "${workspaceName}" created`,
                        color: 'green',
                    });

                    // Refresh workspaces list
                    onCreateWorkspace && onCreateWorkspace();
                    //add to the list of workspaces
                    setWorkspaces([...workspaces, {
                        id: data.id,
                        workspace_uuid: data.workspace_uuid,
                        workspace_name: data.workspace_name,
                        creation_date: data.creation_date
                    }]);
                })
                .catch(error => {
                    console.error("Error creating workspace:", error);
                    onError && onError(`Failed to create workspace: ${error instanceof Error ? error.message : String(error)}`);

                    // Reset search value to what the user had typed to allow retrying
                    setSearchValue(nameToCreate);

                    // Show error notification
                    notifications.show({
                        title: 'Error',
                        message: `Failed to create workspace: ${error instanceof Error ? error.message : String(error)}`,
                        color: 'red',
                    });
                })
                .finally(() => {
                    setIsCreatingWorkspace(false);
                });
        } catch (error) {
            console.error("Error in handleCreateFromSearch:", error);
            setIsCreatingWorkspace(false);
            onError && onError(`Error: ${error instanceof Error ? error.message : String(error)}`);
        }
    }
    return (

        <>
            {/* Confirmation modal to delete workspace */}
            <Modal
                opened={deleteModalOpen}
                onClose={() => setDeleteModalOpen(false)}
                title={<Title order={4} c="red.7">Delete Workspace</Title>}
                centered
                size="md"
                radius="md"
                padding="xl"
                zIndex={1000}
                styles={{
                    header: {
                        backgroundColor: theme.colors.gray[0],
                        borderBottom: `1px solid ${theme.colors.gray[2]}`,
                        padding: '15px 20px'
                    },
                    body: { padding: '20px' },
                    overlay: {
                        zIndex: 1000
                    },
                    inner: {
                        zIndex: 1000
                    }
                }}
            >
                <Stack>
                    <Group>
                        <ThemeIcon color="red" size="lg" radius="xl">
                            <FaExclamationCircle />
                        </ThemeIcon>
                        <Text size="lg" fw={500}>Are you sure?</Text>
                    </Group>

                    <Text>
                    </Text>

                    <Text size="sm" c="dimmed" mt="xs">
                        All implants associated with this workspace will be returned to the default group.
                    </Text>

                    <Divider my="md" />

                    <Group justify="space-between">
                        <Button
                            variant="subtle"
                            onClick={() => setDeleteModalOpen(false)}
                        >
                            Cancel
                        </Button>

                        <Button
                            color="red"
                            leftSection={<FaTrash size={14} />}
                            onClick={confirmDeleteWorkspace}
                        >
                            Delete Workspace
                        </Button>
                    </Group>
                </Stack>
            </Modal>

            <Paper p="md" radius="md" withBorder>
                <Stack>
                    <Group justify="apart">
                        <Title order={5}>Workspace</Title>
                        <Badge color="gray" variant="light">Optional</Badge>
                    </Group>

                    <Select
                        placeholder="Search or create workspace"
                        label="Assign to workspace"
                        leftSection={<FaFolder size={14} />}
                        data={workspaceSelectData}
                        value={selectedWorkspace}
                        onChange={setSelectedWorkspace}
                        clearable
                        searchable
                        searchValue={searchValue}
                        onSearchChange={setSearchValue}
                        disabled={disabled || isCreatingWorkspace}
                        styles={{
                            root: { marginBottom: 10 },
                            input: { borderRadius: 8 },
                            dropdown: { maxHeight: 200 }
                        }}
                        renderOption={({ option }) => (
                            <CustomSelectOption option={option} />
                        )}
                    />

                    {searchValue.trim() !== '' && !searchValueExists && !isCreatingWorkspace && (
                        <Button
                            onClick={handleCreateFromSearch}
                            onMouseDown={() => {
                                console.log("Mouse down on create workspace button");
                                handleCreateFromSearch();
                            }}
                            leftSection={<FaPlus size={14} />}
                            size="xs"
                            color="dark"
                            variant="gradient"
                            gradient={{ from: 'gray.5', to: 'dark', deg: 45 }}
                            styles={{
                                root: {
                                    marginTop: -5,
                                    position: 'relative',
                                    zIndex: 10,
                                    boxShadow: theme.shadows.xs,
                                    transition: 'all 0.2s ease',
                                    '&:hover': {
                                        transform: 'translateY(-1px)',
                                        boxShadow: theme.shadows.sm
                                    }
                                }
                            }}
                            fullWidth
                        >
                            Create "{searchValue}" workspace
                        </Button>
                    )}
                </Stack>
            </Paper>
        </>
    )
}

export default Workspace;